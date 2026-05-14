#!/usr/bin/env python3
"""
LinkedIn Company Page Poster
Reads posts from a file and publishes them to your LinkedIn company page.
"""

import os
import sys
import json
import argparse
import re
import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
from dateutil import parser as date_parser

# Load environment variables
load_dotenv()

LINKEDIN_ACCESS_TOKEN = os.getenv('LINKEDIN_ACCESS_TOKEN')
LINKEDIN_COMPANY_PAGE_URN = os.getenv('LINKEDIN_COMPANY_PAGE_URN')
LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID')
LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# LinkedIn API endpoints
# Using the newer Posts API (replaces deprecated ugcPosts API)
POSTS_API = 'https://api.linkedin.com/rest/posts'
IMAGES_API = 'https://api.linkedin.com/v2/images'
# LinkedIn API version (format: YYYYMM)
LINKEDIN_API_VERSION = '202601'  # January 2026 (202502 sunset)


def load_posts_from_file(file_path='posts.txt'):
    """Load posts from a text file"""
    posts = []
    
    if not os.path.exists(file_path):
        print(f"❌ ERROR: File '{file_path}' not found")
        return posts
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            posts.append({
                'content': line,
                'line': line_num
            })
    
    return posts


def load_posts_from_json(file_path='posts.json'):
    """Load posts from a JSON file"""
    posts = []
    
    if not os.path.exists(file_path):
        return posts, None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            original_data = data  # Keep reference to original structure
            
            if isinstance(data, list):
                # Handle array of posts
                for item in data:
                    if isinstance(item, dict):
                        content = item.get('content', '')
                        if content:
                            post_data = item.copy()  # Preserve all fields
                            post_data.pop('text', None)  # Remove legacy text field
                            posts.append(post_data)
                    elif isinstance(item, str):
                        # Handle array of strings
                        posts.append({'content': item})
            elif isinstance(data, dict) and 'posts' in data:
                posts = data['posts']
                original_data = data
            else:
                original_data = None
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Invalid JSON in '{file_path}': {e}")
        return [], None
    
    return posts, original_data


def is_posted(post):
    """Check if a post has already been posted"""
    # Check for various posted indicators
    if post.get('posted') == True or post.get('posted') == 'true':
        return True
    if post.get('status') == 'posted' or post.get('status') == 'published':
        return True
    if post.get('postedAt') or post.get('postedDate'):
        return True
    return False


def save_posts_json(file_path, posts_data, original_structure):
    """Save posts back to JSON file, preserving structure"""
    try:
        # If we have the original structure and it was a dict with 'posts' key
        if isinstance(original_structure, dict) and 'posts' in original_structure:
            original_structure['posts'] = posts_data
            data_to_save = original_structure
        else:
            # Otherwise, save as array
            data_to_save = posts_data
        
        # Create backup
        backup_path = file_path + '.backup'
        if os.path.exists(file_path):
            import shutil
            shutil.copy2(file_path, backup_path)
        
        # Write updated data
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        
        # Remove backup if successful
        if os.path.exists(backup_path):
            os.remove(backup_path)
        
        return True
    except Exception as e:
        print(f"⚠ Warning: Could not save updated posts to '{file_path}': {e}")
        # Restore backup if save failed
        backup_path = file_path + '.backup'
        if os.path.exists(backup_path):
            import shutil
            shutil.copy2(backup_path, file_path)
            print(f"  Restored from backup")
        return False


def mark_as_posted(post, post_id=None, image_path=None):
    """Mark a post as posted with timestamp and optional image path"""
    post['posted'] = True
    post['postedAt'] = datetime.now(timezone.utc).isoformat()
    post['status'] = 'posted'
    if post_id:
        post['linkedInPostId'] = post_id
    if image_path:
        post['generatedImage'] = image_path


def should_post_now(post, check_schedule=True):
    """Determine if a post should be published now based on postingDate"""
    if not check_schedule:
        return True
    
    posting_date = post.get('postingDate') or post.get('scheduled')
    
    # If no date specified, skip it (don't post)
    if not posting_date or posting_date.strip() == '':
        return False
    
    try:
        # Parse the date - handles multiple formats:
        # - YYYY-MM-DD (treated as 9 AM UTC on that date)
        # - YYYY-MM-DDTHH:MM:SS (with or without timezone)
        # - ISO 8601 formats
        posting_date_clean = posting_date.strip()
        
        # Check if it's a simple date-only format (YYYY-MM-DD)
        is_date_only = (len(posting_date_clean) == 10 and 
                       posting_date_clean.count('-') == 2 and
                       'T' not in posting_date_clean and
                       ' ' not in posting_date_clean)
        
        scheduled_time = date_parser.parse(posting_date)
        
        # If only a date was provided (no time), default to 9 AM UTC
        # This is more reasonable than midnight for most use cases
        if is_date_only:
            scheduled_time = scheduled_time.replace(hour=9, minute=0, second=0)
        
        # Ensure timezone awareness
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        
        # Compare with current time
        now = datetime.now(timezone.utc)
        return now >= scheduled_time
    except (ValueError, TypeError) as e:
        print(f"⚠ Warning: Could not parse postingDate '{posting_date}': {e}")
        print("  Skipping post...")
        return False


def prepare_text_for_linkedin(text):
    """
    Prepare text for LinkedIn API posting.
    
    LinkedIn API supports:
    - Plain text
    - Newlines (\n) for line breaks
    - Hashtags (#hashtag)
    - Mentions (@[Name](urn:li:person:1234)) - requires URN
    
    LinkedIn API does NOT support:
    - Markdown formatting (bold, italic, etc.)
    - HTML tags
    - Rich text formatting
    
    This function ensures text is properly formatted.
    """
    # Ensure text is a string
    if not isinstance(text, str):
        text = str(text)
    
    # LinkedIn supports \n for line breaks - ensure they're preserved
    # The API will handle them correctly when sent as JSON
    return text


def generate_image_with_gemini(image_prompt, output_path=None, dry_run=False):
    """
    Generate an image using Google Gemini API based on the imagePrompt.
    
    Args:
        image_prompt: Text description of the image to generate
        output_path: Optional path to save the image (default: images/generated_<timestamp>.png)
        dry_run: If True, skip actual generation and just log what would happen
    
    Returns:
        Path to generated image file, or None if generation failed
    """
    if not image_prompt or not image_prompt.strip():
        return None
    
    if not GEMINI_API_KEY or GEMINI_API_KEY == 'your_gemini_api_key_here':
        if not dry_run:
            print("⚠ Warning: GEMINI_API_KEY not set in .env file")
            print("   Image generation skipped. Add your Gemini API key to enable.")
        return None
    
    if dry_run:
        print(f"  [DRY RUN] Would generate image with prompt: {image_prompt[:80]}...")
        return "dry-run-image-path.png"
    
    try:
        from google import genai
        from google.genai import types
        from PIL import Image
        import time
        
        # Initialize Gemini client
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Generate image using Gemini's image generation model
        print(f"  Generating image: {image_prompt[:60]}...")
        
        # Try different models - imagen models may have better free tier access
        models_to_try = [
            "imagen-3",
            "imagen-3-fast-generate-001", 
            "gemini-2.0-flash-exp-image-generator",
            "gemini-2.5-flash-image"
        ]
        
        response = None
        last_error = None
        
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[image_prompt],
                )
                print(f"  ✓ Success with model: {model_name}")
                break
            except Exception as e:
                last_error = e
                error_str = str(e)
                if '429' not in error_str and 'quota' not in error_str.lower() and 'not found' not in error_str.lower():
                    # If it's not quota or not found, this model doesn't exist
                    continue
                # If it's quota or not found, try next model
                continue
        
        if response is None:
            raise last_error if last_error else Exception("No suitable model found")
        
        # Save the generated image
        if output_path is None:
            # Create images directory if it doesn't exist
            os.makedirs('images', exist_ok=True)
            timestamp = int(time.time())
            output_path = f"images/generated_{timestamp}.png"
        
        # Extract and save image from response
        image_saved = False
        for part in response.parts:
            if hasattr(part, 'inline_data') and part.inline_data is not None:
                # Get image data
                if hasattr(part, 'as_image'):
                    image = part.as_image()
                    # Check if it's a PIL Image or needs conversion
                    if hasattr(image, 'save'):
                        image.save(output_path)
                    else:
                        # Try to get bytes and create PIL Image
                        from PIL import Image as PILImage
                        import io
                        if hasattr(part.inline_data, 'data'):
                            img_data = part.inline_data.data
                            image = PILImage.open(io.BytesIO(img_data))
                            image.save(output_path)
                        else:
                            # Try direct bytes access
                            img_bytes = bytes(part.inline_data)
                            image = PILImage.open(io.BytesIO(img_bytes))
                            image.save(output_path)
                else:
                    # Fallback: try to get data directly
                    from PIL import Image as PILImage
                    import io
                    if hasattr(part.inline_data, 'data'):
                        img_data = part.inline_data.data
                        image = PILImage.open(io.BytesIO(img_data))
                        image.save(output_path)
                    else:
                        continue
                
                image_saved = True
                print(f"  ✓ Image saved to: {output_path}")
                break
        
        if not image_saved:
            print("  ⚠ Warning: No image data found in response")
            return None
        
        return output_path
        
    except ImportError:
        print("  ⚠ Warning: google-genai package not installed")
        print("   Run: pip install google-genai Pillow")
        return None
    except Exception as e:
        print(f"  ❌ Error generating image: {e}")
        return None


def upload_image_to_linkedin(image_path, company_urn, dry_run=False):
    """
    Upload an image to LinkedIn using the Images API and return the image URN.
    
    Args:
        image_path: Path to the image file
        company_urn: Company URN (urn:li:organization:XXXXX)
        dry_run: If True, skip actual upload
    
    Returns:
        Image URN (urn:li:image:XXXXX) or None
    """
    if not os.path.exists(image_path):
        print(f"  ❌ Image file not found: {image_path}")
        return None
    
    if dry_run:
        print(f"  [DRY RUN] Would upload image: {image_path}")
        return "urn:li:image:dry-run-urn"
    
    try:
        # Step 1: Initialize upload to get upload URL (using new Images API)
        initialize_data = {
            "initializeUploadRequest": {
                "owner": company_urn
            }
        }
        
        headers = {
            'Authorization': f'Bearer {LINKEDIN_ACCESS_TOKEN}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0',
            'Linkedin-Version': LINKEDIN_API_VERSION
        }
        
        # Initialize the upload
        initialize_response = requests.post(
            'https://api.linkedin.com/rest/images?action=initializeUpload',
            json=initialize_data,
            headers=headers
        )
        
        if initialize_response.status_code != 200:
            print(f"  ❌ Failed to initialize upload: {initialize_response.status_code}")
            print(f"  Response: {initialize_response.text}")
            
            # Check for permission errors
            if initialize_response.status_code == 400:
                error_data = initialize_response.json() if initialize_response.text else {}
                error_msg = error_data.get('message', '')
                if 'organization permissions' in error_msg.lower():
                    print()
                    print("  ⚠ PERMISSION ERROR:")
                    print("  Your access token doesn't have 'w_organization_social' permission.")
                    print("  Run: python get_access_token.py to regenerate your token")
                    print("  Make sure your LinkedIn app has 'Community Management API' product approved")
            
            return None
        
        initialize_result = initialize_response.json()
        upload_url = initialize_result['value']['uploadUrl']
        image_urn = initialize_result['value']['image']
        
        # Step 2: Upload the image file
        with open(image_path, 'rb') as image_file:
            upload_headers = {
                'Authorization': f'Bearer {LINKEDIN_ACCESS_TOKEN}',
            }
            upload_response = requests.put(upload_url, data=image_file, headers=upload_headers)
            
            if upload_response.status_code not in [200, 201]:
                print(f"  ❌ Failed to upload image: {upload_response.status_code}")
                print(f"  Response: {upload_response.text}")
                return None
        
        print(f"  ✓ Image uploaded successfully: {image_urn}")
        return image_urn
        
    except Exception as e:
        print(f"  ❌ Error uploading image: {e}")
        import traceback
        traceback.print_exc()
        return None


def verify_organization_access(company_urn):
    """Verify that we have access to post as the organization"""
    try:
        url = 'https://api.linkedin.com/v2/organizationalEntityAcls'
        params = {
            'q': 'roleAssignee',
            'role': 'ADMINISTRATOR'
        }
        headers = {
            'Authorization': f'Bearer {LINKEDIN_ACCESS_TOKEN}',
            'X-Restli-Protocol-Version': '2.0.0'
        }
        
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            if 'elements' in data:
                for element in data['elements']:
                    org_urn = element.get('organizationalTarget')
                    if org_urn == company_urn:
                        return True
            print(f"  ⚠ Warning: Organization {company_urn} not found in your accessible organizations")
            return False
        elif response.status_code == 403:
            # 403 is common: organizationalEntityAcls needs rw_organization_admin;
            # w_organization_social (posting) doesn't grant ACL read access
            print(f"  ℹ Skipping org verification (403 - normal if you only have posting permissions)")
            return None
        else:
            print(f"  ⚠ Warning: Could not verify organization access: {response.status_code}")
            return None  # Unknown, but continue anyway
    except Exception as e:
        print(f"  ⚠ Warning: Error verifying organization: {e}")
        return None  # Unknown, but continue anyway


def verify_token_has_org_scope():
    """
    Use LinkedIn token introspection to verify the access token has w_organization_social.
    Returns:
      True if scope is present,
      False if the token is active but missing the scope,
      'inactive' if LinkedIn says the token is inactive/expired,
      None if we couldn't check.
    """
    if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        return None  # Can't introspect without client credentials
    if not LINKEDIN_ACCESS_TOKEN:
        return None

    try:
        response = requests.post(
            'https://www.linkedin.com/oauth/v2/introspectToken',
            data={
                'client_id': LINKEDIN_CLIENT_ID,
                'client_secret': LINKEDIN_CLIENT_SECRET,
                'token': LINKEDIN_ACCESS_TOKEN,
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        if response.status_code != 200:
            return None

        data = response.json()
        if not data.get('active'):
            return 'inactive'

        scope_str = data.get('scope', '') or ''
        scopes = [s.strip() for s in re.split(r'[\s,]+', scope_str) if s.strip()]
        return 'w_organization_social' in scopes
    except Exception:
        return None


def post_to_linkedin(text, company_urn, image_path=None, dry_run=False):
    """Post content to LinkedIn company page"""
    
    if not LINKEDIN_ACCESS_TOKEN:
        print("❌ ERROR: LINKEDIN_ACCESS_TOKEN not set in .env file")
        return None
    
    if not company_urn:
        print("❌ ERROR: LINKEDIN_COMPANY_PAGE_URN not set in .env file")
        print("   Format: urn:li:organization:XXXXX")
        return None
    
    # Verify organization URN format
    if not company_urn.startswith('urn:li:organization:'):
        print(f"❌ ERROR: Invalid organization URN format: {company_urn}")
        print("   Expected format: urn:li:organization:XXXXX")
        return None
    
    # Prepare text for LinkedIn
    formatted_text = prepare_text_for_linkedin(text)
    
    # Upload image if provided
    image_urn = None
    if image_path:
        image_urn = upload_image_to_linkedin(image_path, company_urn, dry_run=dry_run)
        if not image_urn and not dry_run:
            print("  ⚠ Continuing without image due to upload failure")
    
    # Prepare the post data according to LinkedIn Posts API (newer API)
    post_data = {
        "author": company_urn,
        "commentary": formatted_text,  # Uses 'little' text format
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False
    }
    
    # Add media if image is present
    if image_urn:
        post_data["content"] = {
            "media": {
                "id": image_urn,
                "title": "Generated Image"
            }
        }
    
    if dry_run:
        print("  [DRY RUN] Would post to LinkedIn:")
        print(f"  Author: {company_urn}")
        print(f"  Visibility: PUBLIC")
        print(f"  Content length: {len(formatted_text)} characters")
        if image_path:
            print(f"  Image: {image_path}")
            if image_urn:
                print(f"  Image URN: {image_urn}")
        print(f"  Content preview:")
        preview_lines = formatted_text.split('\n')[:5]
        for i, line in enumerate(preview_lines, 1):
            print(f"    {i}. {line[:80]}{'...' if len(line) > 80 else ''}")
        if len(formatted_text.split('\n')) > 5:
            print(f"    ... ({len(formatted_text.split('\n')) - 5} more lines)")
        print(f"  Full content:")
        print("  " + "-" * 60)
        for line in formatted_text.split('\n'):
            print(f"  {line}")
        print("  " + "-" * 60)
        return "dry-run-post-id"
    
    headers = {
        'Authorization': f'Bearer {LINKEDIN_ACCESS_TOKEN}',
        'Content-Type': 'application/json',
        'X-Restli-Protocol-Version': '2.0.0',
        'Linkedin-Version': LINKEDIN_API_VERSION
    }
    
    try:
        response = requests.post(POSTS_API, json=post_data, headers=headers)
        
        if response.status_code == 201:
            # New Posts API returns post ID in x-restli-id header
            post_id = response.headers.get('x-restli-id') or response.headers.get('x-linkedin-id')
            print(f"✓ Post published successfully!")
            print(f"  Post ID: {post_id}")
            return post_id
        else:
            print(f"❌ ERROR: Failed to post (Status {response.status_code})")
            print(f"  Response: {response.text}")
            
            # Provide helpful error messages
            if response.status_code == 400:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('message', '')
                
                if 'organization permissions' in error_msg.lower() or 'organization as' in error_msg.lower():
                    print()
                    print("  ⚠ PERMISSION ERROR:")
                    print("  Your access token doesn't have 'w_organization_social' permission.")
                    print()
                    print("  SOLUTION:")
                    print("  1. Your LinkedIn app MUST have 'Community Management API' product approved")
                    print("     - Go to https://www.linkedin.com/developers/apps")
                    print("     - Select your app → 'Products' tab")
                    print("     - Find 'Community Management API' (Development Tier)")
                    print("     - Click 'Request access' if not already requested")
                    print("     - Wait for approval (may take time)")
                    print()
                    print("  2. Regenerate your access token:")
                    print("     python get_access_token.py")
                    print()
                    print("  3. The new token will include 'w_organization_social' scope")
                    return None
            
            if response.status_code == 403:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('message', '')
                
                if 'author' in error_msg.lower():
                    print()
                    print("  Troubleshooting:")
                    print("  1. Verify your organization URN is correct")
                    print("  2. Ensure you have ADMINISTRATOR role on the organization")
                    print("  3. Check that your access token has 'w_organization_social' scope")
                    print("     (Required for posting to organization pages)")
                    print("  4. Ensure your LinkedIn app has 'Community Management API' product approved")
                    print("  5. Try running: python get_access_token.py to refresh your token")
                    print()
                    print("  To verify your organization URN, check:")
                    print("  - Your LinkedIn app settings")
                    print("  - Or use: https://www.linkedin.com/company/XXXXX/admin/dashboard/")
                    print("    (replace XXXXX with your company ID)")
                
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: Network error: {e}")
        return None


def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Post content to LinkedIn company page from JSON or text file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python linkedin_poster.py              # Post ready items
  python linkedin_poster.py --dry-run    # Preview what would be posted
  python linkedin_poster.py -d           # Short form of dry-run
        """
    )
    parser.add_argument(
        '-d', '--dry-run',
        action='store_true',
        help='Preview posts without actually posting to LinkedIn'
    )
    args = parser.parse_args()
    
    dry_run = args.dry_run
    
    print("=" * 60)
    print("LinkedIn Company Page Poster")
    if dry_run:
        print("  [DRY RUN MODE - No posts will be published]")
    print("=" * 60)
    print()
    
    # Check credentials
    if not LINKEDIN_ACCESS_TOKEN or LINKEDIN_ACCESS_TOKEN == 'your_access_token_here':
        print("❌ ERROR: LINKEDIN_ACCESS_TOKEN not set in .env file")
        print("   Run get_access_token.py first to get your access token")
        sys.exit(1)
    
    if not LINKEDIN_COMPANY_PAGE_URN or LINKEDIN_COMPANY_PAGE_URN == 'urn:li:organization:your_page_id_here':
        print("❌ ERROR: LINKEDIN_COMPANY_PAGE_URN not set in .env file")
        print("   Format: urn:li:organization:XXXXX")
        print("   You can find this in your LinkedIn app settings or company page")
        sys.exit(1)

    # Verify token has w_organization_social scope (requires client_id/secret in .env)
    scope_ok = verify_token_has_org_scope()
    if scope_ok == 'inactive':
        print()
        print("❌ ERROR: Your LinkedIn access token is inactive or expired.")
        print()
        print("   FIX: Run the following to generate a fresh token:")
        print("        python get_access_token.py")
        print()
        sys.exit(1)
    if scope_ok is False:
        print()
        print("❌ ERROR: Your access token does NOT have 'w_organization_social' permission.")
        print()
        print("   This scope is required for posting to organization/company pages.")
        print()
        print("   FIX: Run the following to get a new token with the correct scope:")
        print("        python get_access_token.py")
        print()
        print("   Also verify your LinkedIn app has 'Community Management API' product APPROVED:")
        print("   https://www.linkedin.com/developers/apps → Your App → Products")
        print()
        sys.exit(1)
    elif scope_ok is True:
        print("✓ Token has w_organization_social scope")
    
    print(f"✓ Company Page: {LINKEDIN_COMPANY_PAGE_URN}")
    if dry_run:
        print("✓ Mode: DRY RUN (preview only)")
    else:
        # Verify organization access (non-blocking)
        print("Verifying organization access...")
        verify_result = verify_organization_access(LINKEDIN_COMPANY_PAGE_URN)
        if verify_result is False:
            print("  ⚠ Warning: Could not verify access to this organization")
            print("  Continuing anyway - the API call will confirm permissions...")
        elif verify_result is True:
            print("  ✓ Organization access verified")
        print()
    
    # Determine which file to use - prefer JSON
    file_path = None
    posts = []
    original_structure = None
    
    # Try JSON first, then text file
    if os.path.exists('posts.json'):
        print("Loading posts from posts.json...")
        posts, original_structure = load_posts_from_json('posts.json')
        file_path = 'posts.json'
    elif os.path.exists('posts.txt'):
        print("⚠ Loading posts from posts.txt (consider using posts.json instead)...")
        posts = load_posts_from_file('posts.txt')
        file_path = 'posts.txt'
    else:
        print("❌ ERROR: No posts file found")
        print("   Create posts.json with a JSON array:")
        print('   [{"content": "Your post here"}, {"content": "Another post"}]')
        sys.exit(1)
    
    if not posts:
        print(f"❌ ERROR: No posts found in '{file_path}'")
        print("   Add some posts to the file and try again")
        sys.exit(1)
    
    print(f"✓ Found {len(posts)} post(s) in file")
    print()
    
    # Keep reference to original posts list for saving (for JSON files)
    # Since posts are dicts, modifications are in-place
    all_posts_for_saving = posts if file_path == 'posts.json' else None
    
    # Filter out already posted items (only for JSON files)
    # Create filtered list but keep reference to originals
    if file_path == 'posts.json':
        posted_count = sum(1 for post in posts if is_posted(post))
        if posted_count > 0:
            print(f"ℹ Skipping {posted_count} already posted item(s)")
            print()
        unposted_posts = [post for post in posts if not is_posted(post)]
    else:
        unposted_posts = posts
    
    # Filter posts based on schedule
    posts_scheduled_ready = []
    posts_skipped_future = []
    posts_skipped_no_date = []
    
    for post in unposted_posts:
        posting_date = post.get('postingDate') or post.get('scheduled', '')
        
        # Skip posts with no date
        if not posting_date or posting_date.strip() == '':
            posts_skipped_no_date.append(post)
            continue
        
        # Check if scheduled date has arrived
        if should_post_now(post, check_schedule=True):
            posts_scheduled_ready.append(post)
        else:
            posts_skipped_future.append(post)
    
    # Show summary
    print("Post Status:")
    print("-" * 60)
    print(f"  Ready to post (scheduled): {len(posts_scheduled_ready)}")
    if posts_skipped_future:
        print(f"  Scheduled (future): {len(posts_skipped_future)}")
    if posts_skipped_no_date:
        print(f"  Skipped (no postingDate): {len(posts_skipped_no_date)}")
    print("-" * 60)
    print()
    
    # Log details about skipped posts
    if posts_skipped_future and dry_run:
        print("Future scheduled posts (not ready yet):")
        for i, post in enumerate(posts_skipped_future[:5], 1):  # Show first 5
            text = post.get('content', '')
            date = post.get('postingDate') or post.get('scheduled', '')
            preview = text[:60] + "..." if len(text) > 60 else text
            print(f"  {i}. [{date}] {preview}")
        if len(posts_skipped_future) > 5:
            print(f"  ... and {len(posts_skipped_future) - 5} more")
        print()
    
    if posts_skipped_no_date and dry_run:
        print("Posts skipped (no postingDate):")
        for i, post in enumerate(posts_skipped_no_date[:5], 1):  # Show first 5
            text = post.get('content', '')
            preview = text[:60] + "..." if len(text) > 60 else text
            print(f"  {i}. {preview}")
        if len(posts_skipped_no_date) > 5:
            print(f"  ... and {len(posts_skipped_no_date) - 5} more")
        print()
    
    # Ready posts are only those with valid dates that are ready
    all_ready_posts = posts_scheduled_ready
    
    if not all_ready_posts:
        print("ℹ No posts ready to publish at this time.")
        if posts_skipped_future:
            print("\nFuture scheduled posts:")
            for i, post in enumerate(posts_skipped_future, 1):
                text = post.get('content', '')
                date = post.get('postingDate') or post.get('scheduled', '')
                preview = text[:50] + "..." if len(text) > 50 else text
                print(f"  {i}. [{date}] {preview}")
        if posts_skipped_no_date:
            print(f"\n⚠ {len(posts_skipped_no_date)} post(s) skipped because postingDate is empty.")
            print("   Add a postingDate to schedule these posts.")
        sys.exit(0)
    
    # Show posts to be published
    print("Posts to be published:")
    print("-" * 60)
    for i, post in enumerate(all_ready_posts, 1):
        text = post.get('content', '') if isinstance(post, dict) else str(post)
        preview = text[:60] + "..." if len(text) > 60 else text
        posting_date = post.get('postingDate') or post.get('scheduled', '')
        date_str = f" [{posting_date}]" if posting_date and posting_date.strip() else ""
        print(f"{i}.{date_str} {preview}")
    print("-" * 60)
    print()
    
    # Check if running in interactive mode
    if not dry_run:
        if sys.stdin.isatty():
            response = input("Publish all ready posts? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("Cancelled.")
                sys.exit(0)
        else:
            print("Non-interactive mode: Publishing all ready posts...")
    else:
        print("DRY RUN: Previewing posts (no actual posting)...")
    
    print()
    if dry_run:
        print("=" * 60)
        print("DRY RUN - Preview of posts that would be published:")
        print("=" * 60)
        print()
    else:
        print("Publishing posts...")
        print()
    
    # Post each item
    success_count = 0
    fail_count = 0
    updated_posts = False
    
    for i, post in enumerate(all_ready_posts, 1):
        # Handle both dict and string formats
        if isinstance(post, dict):
            text = post.get('content', '')
        else:
            text = str(post)
        
        if not text:
            print(f"⚠ Post {i}: Empty post, skipping")
            continue
        
        posting_date = post.get('postingDate') or post.get('scheduled', '')
        date_str = f" (scheduled: {posting_date})" if posting_date and posting_date.strip() else ""
        
        # Generate image if imagePrompt is present
        image_path = None
        image_prompt = post.get('imagePrompt', '') if isinstance(post, dict) else ''
        
        if image_prompt and image_prompt.strip():
            if dry_run:
                print(f"[{i}/{len(all_ready_posts)}] Post Preview:")
                print(f"  Scheduled Date: {posting_date if posting_date else 'N/A'}")
                print(f"  Content Length: {len(text)} characters")
                print(f"  Line Count: {len(text.split(chr(10)))} lines")
                print(f"  Image Prompt: {image_prompt[:60]}...")
            else:
                print(f"Posting {i}/{len(all_ready_posts)}: {text[:50]}...{date_str}")
                print(f"  Generating image from prompt...")
            
            # Generate image
            image_path = generate_image_with_gemini(image_prompt, dry_run=dry_run)
            
            if image_path and not dry_run:
                print(f"  ✓ Image generated: {image_path}")
        else:
            if dry_run:
                print(f"[{i}/{len(all_ready_posts)}] Post Preview:")
                print(f"  Scheduled Date: {posting_date if posting_date else 'N/A'}")
                print(f"  Content Length: {len(text)} characters")
                print(f"  Line Count: {len(text.split(chr(10)))} lines")
                print(f"  No image prompt - text-only post")
            else:
                print(f"Posting {i}/{len(all_ready_posts)}: {text[:50]}...{date_str}")
        
        # Post to LinkedIn (with image if available)
        post_id = post_to_linkedin(text, LINKEDIN_COMPANY_PAGE_URN, image_path=image_path, dry_run=dry_run)
        
        if post_id:
            success_count += 1
            # Mark as posted (only for JSON files and not in dry run)
            if not dry_run and file_path == 'posts.json' and isinstance(post, dict):
                mark_as_posted(post, post_id, image_path=image_path)
                updated_posts = True
        else:
            fail_count += 1
        
        print()
    
    # Save updated posts back to JSON file (only if not dry run)
    # Since posts are dictionaries and we modify them in-place, 
    # all_posts_for_saving already has the updates
    if not dry_run and updated_posts and file_path == 'posts.json' and all_posts_for_saving:
        print("Saving updated post status...")
        if save_posts_json(file_path, all_posts_for_saving, original_structure):
            print("✓ Post status saved successfully")
        else:
            print("⚠ Could not save post status - posts may be reposted on next run")
        print()
    
    # Summary
    print("=" * 60)
    if dry_run:
        print("DRY RUN Summary:")
        print(f"  Previewed posts: {success_count}")
        print(f"  Would post: {success_count} post(s)")
        if fail_count > 0:
            print(f"  Would fail: {fail_count}")
        print()
        print("  Note: No posts were actually published.")
        print("  Run without --dry-run to publish these posts.")
    else:
        print("Summary:")
        print(f"  ✓ Successfully posted: {success_count}")
        if fail_count > 0:
            print(f"  ❌ Failed: {fail_count}")
    print("=" * 60)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
