# Railway Deployment Configuration

## CSRF Cookie Issue Fix

When deploying the web app and API on separate Railway domains, cookies need special configuration to work cross-origin.

### Required Environment Variables for API Service

Add these to your Railway API service environment:

```bash
# Cookie settings for cross-origin (separate web/API domains)
CSRF_COOKIE_SAMESITE=none
CSRF_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
SESSION_COOKIE_SECURE=true

# CORS - Add your web app URL
WEB_ALLOWED_ORIGINS=https://web-production-9c714.up.railway.app

# Optional: If you want to share cookies across subdomains later
# SESSION_COOKIE_DOMAIN=.railway.app
```

### Required Environment Variables for Web Service

```bash
# Point to your API service URL
NEXT_PUBLIC_API_BASE_URL=https://api-production-XXXX.up.railway.app
```

## Why This Is Needed

1. **SameSite=lax** (default) prevents cookies from being sent in cross-site POST requests
2. **SameSite=none** allows cross-origin cookies but requires **Secure=true**
3. Railway deploys each service on a different subdomain, making them cross-origin
4. The CSRF validation requires both the header AND cookie to match

## Alternative: Same-Domain Deployment

If you want to avoid cross-origin issues entirely, deploy both services behind a single domain using:
- Railway's custom domains feature
- A reverse proxy (nginx/Caddy) routing `/api/*` to the API service
