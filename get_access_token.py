#!/usr/bin/env python3
"""
LinkedIn OAuth 2.0 Access Token Generator
This script helps you obtain an access token for posting to your LinkedIn company page.
"""

import os
import sys
import urllib.parse
import http.server
import socketserver
import webbrowser
from urllib.parse import parse_qs, urlparse
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID')
CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET')
REDIRECT_PORT = int(os.getenv('REDIRECT_PORT', '8000'))
REDIRECT_URI = f'http://localhost:{REDIRECT_PORT}/callback'

# Required scopes for posting to company pages
# w_organization_social: Required for posting to organization/company pages
# w_member_social: Required for posting on behalf of authenticated member
# Note: For organization posts, you need w_organization_social permission
# which requires your LinkedIn app to have the "Community Management API" product approved
# 
# If you get "invalid_scope_error", it means Community Management API is not approved yet.
# In that case, we'll try requesting just w_organization_social first, then fall back to w_member_social
SCOPES = ['w_organization_social', 'w_member_social']

class CallbackHandler(http.server.SimpleHTTPRequestHandler):
    """Handle OAuth callback"""
    
    def do_GET(self):
        """Handle GET request from LinkedIn redirect"""
        if self.path.startswith('/callback'):
            # Parse the authorization code from the callback URL
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            if 'code' in query_params:
                auth_code = query_params['code'][0]
                self.server.auth_code = auth_code
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"""
                    <html>
                    <body>
                        <h1>Authorization Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                """)
            elif 'error' in query_params:
                error = query_params['error'][0]
                error_description = query_params.get('error_description', ['Unknown error'])[0]
                self.server.auth_error = error
                self.server.auth_error_description = error_description
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(f"""
                    <html>
                    <body>
                        <h1>Authorization Failed</h1>
                        <p><strong>Error:</strong> {error}</p>
                        <p><strong>Description:</strong> {error_description}</p>
                        <p>Please check the terminal for detailed troubleshooting steps.</p>
                    </body>
                    </html>
                """.encode())
                self.server.auth_code = None
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


def get_authorization_url():
    """Generate LinkedIn authorization URL"""
    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'state': 'random_state_string',
        'scope': ' '.join(SCOPES)
    }
    
    auth_url = 'https://www.linkedin.com/oauth/v2/authorization?' + urllib.parse.urlencode(params)
    return auth_url


def exchange_code_for_token(auth_code):
    """Exchange authorization code for access token"""
    token_url = 'https://www.linkedin.com/oauth/v2/accessToken'
    
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    response = requests.post(token_url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    
    if response.status_code == 200:
        token_data = response.json()
        return token_data.get('access_token')
    else:
        print(f"Error exchanging code for token: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def get_company_pages(access_token):
    """Get list of company pages the user has access to"""
    url = 'https://api.linkedin.com/v2/organizationalEntityAcls'
    params = {
        'q': 'roleAssignee',
        'role': 'ADMINISTRATOR'
    }
    headers = {
        'Authorization': f'Bearer {access_token}',
        'X-Restli-Protocol-Version': '2.0.0'
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching company pages: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def main():
    """Main OAuth flow"""
    print("=" * 60)
    print("LinkedIn OAuth 2.0 Access Token Generator")
    print("=" * 60)
    print()
    
    # Check if credentials are set
    if not CLIENT_ID or CLIENT_ID == 'your_client_id_here':
        print("❌ ERROR: LINKEDIN_CLIENT_ID not set in .env file")
        print("Please add your Client ID to the .env file first.")
        sys.exit(1)
    
    if not CLIENT_SECRET or CLIENT_SECRET == 'your_client_secret_here':
        print("❌ ERROR: LINKEDIN_CLIENT_SECRET not set in .env file")
        print("Please add your Client Secret to the .env file first.")
        sys.exit(1)
    
    print("✓ Credentials loaded from .env file")
    print()
    
    # Verify redirect URI and permissions are configured in LinkedIn app
    print("=" * 60)
    print("⚠️  SETUP REQUIRED:")
    print("=" * 60)
    print(f"1. Add redirect URI to your LinkedIn app: {REDIRECT_URI}")
    print()
    print("2. Request required permissions:")
    print("   - Go to https://www.linkedin.com/developers/apps")
    print("   - Select your app → 'Products' tab")
    print("   - Click 'Request access' for 'Community Management API' (Development Tier)")
    print("   - Fill out the access request form with your use case")
    print("   - This grants the 'w_organization_social' scope needed for organization posts")
    print("   - ⚠ IMPORTANT: You MUST have 'Community Management API' product APPROVED")
    print("     before running this script (otherwise you'll get 'invalid_scope_error')")
    print("   - If you see 'invalid_scope_error', check if the product is approved")
    print("   - If you see an exclusivity error, create a NEW app (see SETUP_NEW_APP.md)")
    print()
    print("3. Add redirect URI:")
    print("   - Go to 'Auth' tab")
    print(f"   - Add redirect URL: {REDIRECT_URI}")
    print("   - Click 'Update'")
    print("=" * 60)
    print()
    
    # Step 1: Find available port and start server
    print("Step 1: Starting callback server...")
    handler = CallbackHandler
    httpd = None
    actual_port = REDIRECT_PORT
    actual_redirect_uri = REDIRECT_URI
    
    # Initialize error tracking
    auth_error = None
    auth_error_description = None
    
    try:
        httpd = socketserver.TCPServer(("", actual_port), handler)
        print(f"✓ Server started on port {actual_port}")
    except OSError as e:
        print(f"❌ ERROR: Could not bind to port {actual_port}")
        print(f"   Error: {e}")
        print()
        print(f"   Port {actual_port} is already in use.")
        print("   Options:")
        print(f"   1. Free up port {actual_port} (kill the process using it)")
        print(f"   2. Change REDIRECT_PORT in .env to a different port (e.g., 8001)")
        print("      Then update your LinkedIn app redirect URI to match")
        print()
        print("   To find what's using the port:")
        print(f"   lsof -i :{actual_port}")
        sys.exit(1)
    
    print()
    
    # Step 2: Generate authorization URL
    print("Step 2: Generating authorization URL...")
    auth_url = get_authorization_url()
    print(f"✓ Authorization URL generated")
    print()
    
    # Step 3: Show callback info
    print("Step 3: Callback server ready")
    print(f"   Listening on {REDIRECT_URI}")
    print()
    
    with httpd:
        httpd.auth_code = None
        httpd.auth_error = None
        httpd.auth_error_description = None
        
        # Step 4: Open browser for authorization
        print("Step 4: Authorization required")
        print("=" * 60)
        print("Please open this URL in your browser:")
        print(auth_url)
        print("=" * 60)
        print()
        print("After authorizing, you'll be redirected back and the script will continue.")
        print()
        
        try:
            webbrowser.open(auth_url)
            print("✓ Browser opened automatically")
        except:
            print("⚠ Could not open browser automatically - please copy the URL above")
        
        print()
        print("Waiting for authorization callback...")
        print("(The script will wait up to 5 minutes)")
        print()
        
        # Wait for callback
        httpd.timeout = 300  # 5 minute timeout
        httpd.handle_request()
        
        auth_code = httpd.auth_code
        auth_error = httpd.auth_error
        auth_error_description = httpd.auth_error_description
    
    if not auth_code:
        if auth_error == 'invalid_scope_error':
            print()
            print("=" * 60)
            print("⚠️  INVALID SCOPE ERROR")
            print("=" * 60)
            print()
            print("The scope 'w_organization_social' is not available because:")
            print("  1. Your LinkedIn app doesn't have 'Community Management API' product APPROVED")
            print("  2. OR you're using an app that already has other products (exclusivity requirement)")
            print()
            print("SOLUTION:")
            print("  1. Check your app's Products tab:")
            print("     https://www.linkedin.com/developers/apps")
            print("  2. If 'Community Management API' shows as 'Requested' (not 'Approved'):")
            print("     - Wait for LinkedIn's approval (may take days)")
            print("     - Check your email for approval notifications")
            print("  3. If you see an exclusivity error when requesting:")
            print("     - Create a NEW app specifically for Community Management API")
            print("     - See SETUP_NEW_APP.md for detailed instructions")
            print("  4. Once approved, run this script again")
            print()
            print("Current scopes requested:", ', '.join(SCOPES))
            print("=" * 60)
            sys.exit(1)
        print("❌ ERROR: No authorization code received")
        if auth_error:
            print(f"Error: {auth_error}")
            print(f"Description: {auth_error_description}")
        print("Please make sure you authorized the app and that the redirect URI matches.")
        sys.exit(1)
    
    print("✓ Authorization code received")
    print()
    
    # Step 5: Exchange code for access token
    print("Step 5: Exchanging authorization code for access token...")
    access_token = exchange_code_for_token(auth_code)
    
    if not access_token:
        print("❌ ERROR: Failed to get access token")
        sys.exit(1)
    
    print("✓ Access token obtained")
    print()
    
    # Step 6: Get company pages (optional - may not work without r_organization_social scope)
    print("Step 6: Attempting to fetch your company pages...")
    pages = get_company_pages(access_token)
    
    if pages and 'elements' in pages and len(pages['elements']) > 0:
        print(f"✓ Found {len(pages['elements'])} company page(s):")
        print()
        for i, page in enumerate(pages['elements'], 1):
            org_urn = page.get('organizationalTarget')
            print(f"  {i}. {org_urn}")
        print()
        print("Copy the URN (urn:li:organization:XXXXX) and add it to your .env file")
        print("as LINKEDIN_COMPANY_PAGE_URN")
    else:
        print("⚠ Could not fetch company pages automatically")
        print("This is normal if you don't have the r_organization_social scope.")
        print()
        print("To find your company page URN manually:")
        print("1. Go to your company page on LinkedIn")
        print("2. The URN format is: urn:li:organization:XXXXX")
        print("3. You can also check your LinkedIn app settings")
        print("4. Add it to your .env file as LINKEDIN_COMPANY_PAGE_URN")
    print()
    
    # Step 7: Save token
    print("Step 7: Saving access token...")
    print()
    print("=" * 60)
    print("SUCCESS! Your access token:")
    print("=" * 60)
    print(access_token)
    print()
    print("Add this to your .env file as:")
    print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
    print()
    print("⚠️  IMPORTANT:")
    print("   1. Access tokens expire after 60 days.")
    print("   2. If you get 'Organization permissions must be used' errors when posting:")
    print("      - Your LinkedIn app needs 'Community Management API' product APPROVED")
    print("      - Check: https://www.linkedin.com/developers/apps → Your App → Products")
    print("      - The approval process may take time")
    print("   3. Requested scopes:", ', '.join(SCOPES))
    print("      (w_organization_social is required for organization posts)")
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
