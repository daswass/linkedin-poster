# LinkedIn Company Page Poster

Automate posting to your LinkedIn company page from a simple text or JSON file.

## Setup

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   This includes:

   - `requests` - For LinkedIn API calls
   - `python-dotenv` - For environment variable management
   - `python-dateutil` - For date parsing
   - `google-genai` - For Gemini image generation
   - `Pillow` - For image processing

2. **Configure credentials:**

   - Copy `.env.example` to `.env` (if not already done)
   - Add your LinkedIn API credentials:
     - `LINKEDIN_CLIENT_ID`
     - `LINKEDIN_CLIENT_SECRET`
     - `LINKEDIN_ACCESS_TOKEN` (run `get_access_token.py` to get this)
     - `LINKEDIN_COMPANY_PAGE_URN` (format: `urn:li:organization:XXXXX`)
   - **Optional** - For image generation:
     - `GEMINI_API_KEY` - Get from https://aistudio.google.com/app/apikey

   **⚠️ Important:** If you already have a LinkedIn app with "Share on LinkedIn" product, you'll need to create a **new app** for organization posting because "Community Management API" requires exclusivity. See `SETUP_NEW_APP.md` for detailed instructions.

3. **Get your access token:**

   ```bash
   python get_access_token.py
   ```

   This will guide you through the OAuth flow to get your access token.

4. **Find your company page URN:**
   - Check your LinkedIn app settings
   - Or visit your company page on LinkedIn
   - Format: `urn:li:organization:XXXXX`

## Usage

### Quick Start Tasks

You can use the predefined tasks in VS Code or run commands directly:

**VS Code Tasks:**
- Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
- Type "Tasks: Run Task"
- Select:
  - `LinkedIn Poster: Dry Run` - Preview posts without posting
  - `LinkedIn Poster: Post Ready Items` - Post ready items to LinkedIn
  - `LinkedIn Poster: Test Image Generation` - Test image generation
  - `LinkedIn Poster: Get Access Token` - Get OAuth token

**Command Line:**
```bash
# Dry run (preview)
python linkedin_poster.py --dry-run

# Post ready items
python linkedin_poster.py

# Test image generation
python test_image_generation.py

# Get access token
python get_access_token.py

# Refresh access token, if LinkedIn returned LINKEDIN_REFRESH_TOKEN
python refresh_access_token.py
```

### Option 1: Simple Text File (posts.txt)

Create a file called `posts.txt` with one post per line:

```
Welcome to our company! We're excited to share our latest updates.

Check out our new product launch - it's going to revolutionize the industry!

Join us for our upcoming webinar on industry trends and best practices.
```

Lines starting with `#` are treated as comments and ignored.

### Option 2: JSON File (posts.json) - Recommended

Create a file called `posts.json` with a JSON array. Use the `content` field for post text:

```json
[
  {
    "content": "Welcome to our company! We're excited to share our latest updates.",
    "postingDate": ""
  },
  {
    "content": "Check out our new product launch - it's going to revolutionize the industry!",
    "postingDate": "2026-02-10T10:00:00Z"
  },
  {
    "content": "Join us for our upcoming webinar on industry trends and best practices.",
    "postingDate": "2026-02-15T14:30:00Z",
    "imagePrompt": "Optional: description for AI image generation"
  }
]
```

**Fields:**

- `content` (required): The post text
- `postingDate` (required): Date string in format `YYYY-MM-DD` or full ISO 8601 datetime (e.g., "2026-02-10" or "2026-02-10T10:00:00Z"). Posts with empty `postingDate` will be skipped
- `imagePrompt` (optional): Text description for AI image generation using Google Gemini. If provided, an image will be generated and included with the post.
- `posted` (auto-added): Automatically set to `true` after successful posting
- `postedAt` (auto-added): Timestamp when the post was published
- `linkedInPostId` (auto-added): LinkedIn's post ID for the published post
- `generatedImage` (auto-added): Path to the generated image file (e.g., `images/generated_1234567890.png`) - only added if image was generated

### Image Generation

The script supports automatic image generation using Google's Gemini API:

1. **Setup**: Add your `GEMINI_API_KEY` to the `.env` file

   - Get your API key from: https://aistudio.google.com/app/apikey
   - Add it to `.env`: `GEMINI_API_KEY=your_api_key_here`

2. **Usage**: Include an `imagePrompt` field in your post JSON:

   ```json
   {
     "content": "Your post text here",
     "postingDate": "2026-02-10",
     "imagePrompt": "Professional illustration of a property management dashboard"
   }
   ```

3. **How it works**:
   - When a post has an `imagePrompt`, the script generates an image using Gemini
   - The image is saved to the `images/` directory
   - The image is uploaded to LinkedIn and attached to the post
   - If image generation fails, the post is still published as text-only

**Note**: Generated images are saved locally in the `images/` directory for your records.

### Text Formatting

**Supported:**

- **Newlines**: Use `\n` in your JSON for line breaks (they will be preserved)
- **Hashtags**: Use `#hashtag` format - LinkedIn will automatically link them
- **Plain text**: All standard text characters

**Not Supported:**

- ❌ Markdown formatting (bold, italic, headers, etc.)
- ❌ HTML tags
- ❌ Rich text formatting

**Example with line breaks:**

```json
{
  "content": "First line\n\nSecond line after blank line\nThird line",
  "postingDate": ""
}
```

**Note:** In JSON, `\n` represents a newline character. For multiple paragraphs, use `\n\n` for blank lines between paragraphs.

### Posting

Run the poster script:

```bash
python linkedin_poster.py
```

**Dry Run Mode** (preview without posting):

```bash
python linkedin_poster.py --dry-run
# or short form:
python linkedin_poster.py -d
```

The script will:

1. Load posts from `posts.json` (or `posts.txt` as fallback)
2. Skip posts that are already marked as `posted: true`
3. Check which posts are ready based on `postingDate`
4. Show you a preview of posts ready to publish
5. Ask for confirmation before posting (skipped in dry-run mode)
6. Post each ready item to your LinkedIn company page (or preview in dry-run mode)
7. **Automatically mark posts as posted** and save the updated status back to `posts.json` (skipped in dry-run mode)

**Dry Run Mode:**

- Use `--dry-run` or `-d` flag to preview posts without posting
- Shows detailed information: content preview, length, line count, full text
- Lists all skipped posts (no date, future dates, already posted)
- No changes are made to `posts.json` in dry-run mode
- Perfect for testing and reviewing before actual posting

**Important:** Posts are automatically marked as `posted: true` after successful publishing to prevent duplicate posts. The script creates a backup before saving, so your data is safe.

### Scheduling Posts

**Important:** LinkedIn's API does not support native scheduled publishing. However, this script implements a workaround:

- Posts with empty `postingDate` are skipped (not posted)
- Posts with a future `postingDate` are skipped until that time arrives
- Only posts with a valid `postingDate` that has arrived will be posted
- To use scheduling, run the script periodically (e.g., via cron) to check and post scheduled items

**Example cron job** (runs every hour):

```bash
0 * * * * cd /path/to/linkedin-poster && source venv/bin/activate && python linkedin_poster.py
```

**Date Format:** Supports multiple formats:

- `"2026-02-10"` - Date only (posts at 9:00 AM UTC on that date)
- `"2026-02-10T10:00:00Z"` - Full ISO 8601 with UTC timezone
- `"2026-02-10T10:00:00-05:00"` - Full ISO 8601 with timezone offset
- `"2026-02-10T10:00:00"` - Full ISO 8601 without timezone (assumed UTC)
- Any format parseable by Python's dateutil library

## Troubleshooting

### Error: "Organization permissions must be used when using organization as author"

**Cause:** Your access token doesn't have the `w_organization_social` permission.

**Solution:**

1. **Check your LinkedIn app products:**
   - Go to https://www.linkedin.com/developers/apps
   - Select your app → "Products" tab
   - Find "Community Management API" (Development Tier)
   - Click "Request access" if not already requested
   - Ensure it shows as **APPROVED** (not just requested)
   - Approval can take time - LinkedIn reviews each request

2. **Regenerate your access token:**
   ```bash
   python get_access_token.py
   ```
   - This will request `w_organization_social` scope
   - The scope will only be granted if the product is approved

3. **Verify:**
   - Try posting again: `python linkedin_poster.py --dry-run`
   - If you still get the error, the product may not be approved yet

### Error: 403 Access Denied

- Verify your organization URN is correct (format: `urn:li:organization:XXXXX`)
- Ensure you have ADMINISTRATOR role on the organization
- Check that your access token hasn't expired (tokens expire after 60 days)

### Error: Image upload fails

- Check that your access token has `w_organization_social` permission
- Verify the image file exists and is readable
- Ensure image format is supported (JPG, PNG, GIF)
- Check image size limits (less than 36,152,320 pixels)

## Notes

- Access tokens expire after 60 days. Run `get_access_token.py` again to get a new token.
- **LinkedIn API Limitation:** The LinkedIn API posts immediately when called. True scheduling requires running this script periodically via cron/task scheduler.
- **Required Product:** You MUST have the "Community Management API" product **APPROVED** in your LinkedIn app to post to organization pages. Request it from your app's Products tab.

## Files

- `get_access_token.py` - OAuth script to get your access token
- `linkedin_poster.py` - Main script to post content to LinkedIn
- `posts.txt` - Simple text file format for posts
- `posts.json.example` - Example JSON format for posts
- `.env` - Your credentials (not committed to git)
