# Setting Up Google Search Console OAuth

## Step 1: Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing): `annaseo-gsc`
3. Enable **Google Search Console API**:
   - APIs & Services → Enable APIs → search "Search Console API" → Enable

## Step 2: OAuth Credentials

1. APIs & Services → Credentials → Create Credentials → **OAuth client ID**
2. Application type: **Web application**
3. Name: `ANNASEOv1 GSC`
4. Authorized redirect URIs:
   ```
   http://localhost:8000/api/gsc/auth/callback   (development)
   https://yourdomain.com/api/gsc/auth/callback  (production)
   ```
5. Copy: **Client ID** and **Client Secret**

## Step 3: Add to .env

```bash
GOOGLE_CLIENT_ID=123456789-xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxx
GOOGLE_REDIRECT_URI=http://localhost:8000/api/gsc/auth/callback
```

## Step 4: OAuth Consent Screen

1. APIs & Services → OAuth consent screen
2. User type: External
3. App name: ANNASEOv1
4. Scopes: `https://www.googleapis.com/auth/webmasters.readonly`
5. Test users: add your Google account email

## Step 5: Verify Your Site in GSC

1. Go to [search.google.com/search-console](https://search.google.com/search-console)
2. Add property → URL prefix → your site URL
3. Verify via HTML tag or DNS TXT record
4. Wait for data (usually available within 2-3 days of site traffic)

## OAuth Flow (How It Works)

```
User clicks "Connect GSC"
  → GET /api/gsc/{project_id}/auth/url
  → Returns: { auth_url: "https://accounts.google.com/o/oauth2/auth?..." }
  → Frontend opens auth_url in popup or redirect
  → User logs in to Google + authorizes
  → Google redirects to: /api/gsc/auth/callback?code=...&state={project_id}
  → Backend exchanges code for tokens
  → Tokens saved to gsc_integration_settings
  → Frontend polls /api/gsc/{project_id}/status
  → Status becomes "connected"
```

## Data Available

Once connected, you can fetch:
- **Queries**: The actual search terms users typed
- **Clicks**: Number of clicks your site got for each query
- **Impressions**: How many times Google showed your site for this query
- **CTR**: Click-through rate (clicks / impressions)
- **Position**: Average ranking position

## Important Limits

- GSC API has a **daily quota** (250 queries/day default, can be increased)
- Each fetchQuery call = 1 quota unit
- We batch all queries in **1 API call** (25,000 rows per call)
- Data is available: **last 16 months** (we use last 90 days by default)
- Minimum impressions threshold: **1** (to include any keyword that showed)
