# Connecting the real Instagram account (Meta setup)

Until you finish this guide the app runs with `MOCK_INSTAGRAM=true`: every "publish" is **simulated** and nothing appears on Instagram. The dashboard shows a yellow banner and marks those posts "Published (simulated)".

> Meta renames menus in the App Dashboard from time to time. If a label below doesn't match exactly, look for the closest equivalent. The official guide is "Instagram Platform → Instagram API with Instagram Login" on developers.facebook.com.

---

## What you need

| Requirement | Why |
|---|---|
| An Instagram **Professional** account (Business or Creator) | The official publishing API only works for professional accounts. Personal accounts cannot be automated. |
| A Meta developer account + a Meta app | This gives you the App ID and App Secret. |
| A public **https** address for this application | 1) Instagram's login redirects back to it. 2) Instagram **downloads** each post image from a public URL; it cannot read files on your laptop. |
| Permissions `instagram_business_basic` + `instagram_business_content_publish` | Read the account and publish posts. |

---

## Step 1: Make the Instagram account Professional

On a phone: Instagram app → your profile → ☰ menu → **Settings and activity** → **Account type and tools** → **Switch to professional account** → choose **Business** (or Creator). This is free.

## Step 2: Create a Meta developer account

1. Go to <https://developers.facebook.com/> and log in with the Facebook account of a company administrator.
2. Click **Get Started** and complete the registration (phone/email verification).

## Step 3: Create the app

1. **My Apps** → **Create App**.
2. When asked for a use case, choose the Instagram one (e.g. **"Manage messaging & content on Instagram"**).
3. App type: **Business**. Give it a name such as "Company Social Automation".

## Step 4: Get the App ID and App Secret

In the app, open **Instagram** → **API setup with Instagram login** (sometimes shown as "Instagram API → API setup with Instagram business login").

You will see an **Instagram app ID** and an **Instagram app secret** (click "Show"). These are **not** the same as the Facebook App ID at the top of the dashboard; use the Instagram ones.

Put them in your `.env` file on the server. Never paste them into chat, email or Git:

```
META_APP_ID=<Instagram app ID>
META_APP_SECRET=<Instagram app secret>
```

## Step 5: Register the redirect URL

In the same page, open **Set up Instagram business login** → **Business login settings**, and add this **OAuth redirect URI** (replace the domain with yours):

```
https://social.yourcompany.com/api/instagram/oauth/callback
```

Set exactly the same value in `.env`:

```
META_REDIRECT_URI=https://social.yourcompany.com/api/instagram/oauth/callback
```

It must match character-for-character, including `https` and without a trailing slash.

## Step 6: Allow your Instagram account to use the app

While the app is in **Development** mode, only accounts with a role on the app can connect:

1. App Dashboard → **App roles** → **Roles** → **Add people** → **Instagram Tester** → enter the company's Instagram username.
2. In Instagram (on the web: Settings → **Apps and websites** → **Tester invites**), accept the invitation.

For your **own company account**, this is enough, and no App Review is needed. You would need Meta **App Review** (and Business Verification) only if other businesses will connect their accounts to your app.

## Step 7: Make images publicly reachable

Instagram fetches the image from the URL we send it. Pick one:

- **Option A (simplest):** deploy the app on a server with a domain and HTTPS (see [DEPLOYMENT.md](DEPLOYMENT.md)) and set
  `PUBLIC_BASE_URL=https://social.yourcompany.com`
- **Option B:** use S3-compatible storage with a public-read bucket or CDN:
  `STORAGE_BACKEND=s3`, `S3_BUCKET=…`, `S3_REGION=…`, `S3_ACCESS_KEY_ID=…`, `S3_SECRET_ACCESS_KEY=…`, `S3_PUBLIC_BASE_URL=https://cdn.yourcompany.com`

The app refuses to send `localhost` image URLs to the real API and shows a clear error instead.

> **Testing from a laptop:** use a tunnel such as Cloudflare Tunnel (`cloudflared tunnel --url http://localhost:8080`) or ngrok. Use the https address it prints for `PUBLIC_BASE_URL`, `FRONTEND_URL` and `META_REDIRECT_URI`, and register that redirect URI in Step 5.

## Step 8: Switch off mock mode

In `.env`:

```
MOCK_INSTAGRAM=false
META_LOGIN_TYPE=instagram
META_GRAPH_API_VERSION=v25.0     # check developers.facebook.com/docs/graph-api/changelog for the latest
TOKEN_ENCRYPTION_KEY=<generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
FRONTEND_URL=https://social.yourcompany.com
```

Restart: `docker compose up -d` (it recreates the containers with the new settings).

## Step 9: Connect

1. Log in to the dashboard as an **admin** → **Settings** → **Instagram**.
2. Click **Connect Instagram account**. You are sent to Instagram; log in as the company account and approve the permissions.
3. You return to the dashboard with "connected successfully". The page shows the username, token expiry (about 60 days) and publishing quota.
4. Click **Test connection** to verify the token works.

The access token is encrypted in the database and **never** sent to the browser. It is refreshed automatically before it expires (checked every 6 hours; refreshed when fewer than 15 days remain). If refresh ever fails (for example the password was changed), the status becomes "Token expired" and the dashboard asks you to reconnect.

## Step 10: First real post (recommended procedure)

1. **Settings → General → Pause publishing** (safety switch) while you prepare.
2. Create a test post, generate, review, approve.
3. **Resume publishing**, open the post and click **Publish now**.
4. Check the post detail page: it should say "Published to Instagram" with a **View on Instagram** link. Confirm on the Instagram app.
5. If it fails, the exact Meta error is shown on the post and under **Settings → Logs**.

---

## Alternative: Instagram API with Facebook Login

If the Instagram account is linked to a Facebook Page and you prefer a **non-expiring System User token** from Meta Business Manager:

```
META_LOGIN_TYPE=facebook
META_ACCESS_TOKEN=<system user access token with instagram_basic, instagram_content_publish, pages_read_engagement>
INSTAGRAM_ACCOUNT_ID=<the Instagram Business Account ID (IG user id), not the page id>
```

With these set, the account appears as connected automatically (token source "env"). The "Connect" button is not used in this mode.

---

## Troubleshooting

| Message | Cause / fix |
|---|---|
| "Invalid redirect_uri" on the Instagram login page | `META_REDIRECT_URI` does not exactly match the URI registered in Step 5. |
| "Insufficient developer role" | The Instagram account has not accepted the tester invitation (Step 6). |
| "Instagram access token is invalid or expired" | Reconnect in Settings → Instagram. |
| "The image URL points to localhost…" | Set `PUBLIC_BASE_URL` to a public https URL or use S3 (Step 7). |
| "Instagram could not process the image (container status ERROR)" | Instagram could not download the image. Open the image URL from a phone on mobile data to check it is public. |
| "Instagram publishing limit reached" | Meta allows 100 API-published posts per 24 hours; the app retries automatically later. |
| "Missing Instagram permission" | Reconnect and approve all requested permissions; check the scopes in Step 5. |
