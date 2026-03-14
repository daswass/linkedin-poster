# Setting Up a New LinkedIn App for Organization Posts

Since "Community Management API" requires exclusivity (it must be the only product on an app), you need to create a separate LinkedIn app specifically for organization posting.

## Step 1: Create New LinkedIn App

1. Go to https://www.linkedin.com/developers/apps
2. Click **"Create app"** button
3. Fill in the form:
   - **App name**: `PropMan Poster Organization` (or any name you prefer)
   - **LinkedIn Page**: Select your company page
   - **App use case**: Select "Other" or "Marketing"
   - **App logo**: Upload a logo (optional)
   - **Privacy policy URL**: You can use a placeholder or your company's privacy policy
   - **Terms of service URL**: You can use a placeholder or your company's terms
4. Click **"Create app"**

## Step 2: Request Community Management API

1. In your new app, go to the **"Products"** tab
2. Find **"Community Management API"** (Development Tier)
3. Click **"Request access"**
4. Fill out the access request form:
   - Describe your use case: "Automating posts to our company LinkedIn page"
   - Explain how you'll use it: "Posting scheduled content to engage with our community"
5. Submit the request

## Step 3: Configure Auth Settings

1. Go to the **"Auth"** tab
2. Under **"Redirect URLs"**, add:
   ```
   http://localhost:8000/callback
   ```
3. Click **"Update"**

## Step 4: Get Your Credentials

1. Go to the **"Auth"** tab
2. Copy your:
   - **Client ID**
   - **Client Secret**

## Step 5: Update Your .env File

Update your `.env` file with the new app's credentials:

```bash
LINKEDIN_CLIENT_ID=<new_client_id>
LINKEDIN_CLIENT_SECRET=<new_client_secret>
LINKEDIN_ACCESS_TOKEN=<will_get_this_next>
LINKEDIN_COMPANY_PAGE_URN=urn:li:organization:92756796
GEMINI_API_KEY=<your_gemini_key>
```

## Step 6: Wait for Approval

- LinkedIn will review your Community Management API request
- You'll receive an email when approved (may take a few days)
- Check the Products tab to see approval status

## Step 7: Get Access Token

Once Community Management API is approved:

```bash
python get_access_token.py
```

This will request `w_organization_social` scope, which will now be available.

## Step 8: Test Posting

```bash
python linkedin_poster.py --dry-run
```

## Notes

- Keep your original app ("PropMan Poster") for member posting if needed
- Use the new app specifically for organization page posting
- Both apps can coexist - they're separate applications
- The company page URN stays the same: `urn:li:organization:92756796`
