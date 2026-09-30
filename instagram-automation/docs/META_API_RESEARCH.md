# Meta / Instagram API: what is and isn't possible (verified 2026-09-30)

These findings come from Meta's official Instagram Platform documentation on developers.facebook.com. The documentation host could not be fetched directly from the build environment, so the facts were confirmed through search results that quote the official pages, and the API version is configurable (`META_GRAPH_API_VERSION`). Re-check the linked pages before going live.

## Verified facts used by the implementation

| Topic | Finding | Where used |
|---|---|---|
| Account type | Only Instagram **professional** accounts (Business or Creator) can use the Instagram Platform APIs. | Setup guide |
| API variants | *Instagram API with Instagram Login* (host `graph.instagram.com`, no Facebook Page needed) and *Instagram API with Facebook Login* (host `graph.facebook.com`, account linked to a Page). | `META_LOGIN_TYPE` |
| Permissions (Instagram Login) | `instagram_business_basic`, `instagram_business_content_publish` (also `_manage_messages`, `_manage_comments` for later phases). | `META_OAUTH_SCOPES` |
| OAuth | Authorize at `https://www.instagram.com/oauth/authorize`; exchange the code at `POST https://api.instagram.com/oauth/access_token` for a short-lived token (about 1 hour). | `services/instagram/account.py` |
| Long-lived tokens | `GET graph.instagram.com/access_token?grant_type=ig_exchange_token` gives a token valid **60 days**. Refresh with `grant_type=ig_refresh_token` when the token is at least 24 hours old and still valid; tokens not refreshed within 60 days expire. The app secret is used, so this must happen server-side only. | automatic refresh task |
| Publishing flow | 1) `POST /{ig-user-id}/media` with `image_url` + `caption` creates a **container**; 2) `GET /{container-id}?fields=status_code`; 3) `POST /{ig-user-id}/media_publish` with `creation_id`. | `services/instagram/client.py` |
| Container status | `IN_PROGRESS`, `FINISHED`, `ERROR`, `EXPIRED` (not published within **24 h**), `PUBLISHED`. Meta recommends polling at most once per minute for up to 5 minutes. | duplicate prevention, retries |
| Rate limit | **100** API-published posts per 24-hour moving window (a carousel counts as one). Check with `GET /{ig-user-id}/content_publishing_limit`. | quota check before publishing |
| Images | **JPEG only**, max **8 MB**, aspect ratio between **4:5 and 1.91:1**, and the file must be on a **publicly accessible URL** when the container is created. | template renderer outputs 1080×1350 JPEG |
| Captions | Max 2,200 characters, 30 hashtags, 20 @-mentions. | validation |
| Scheduling | The publishing API publishes immediately when called. It has no parameter to schedule a future Instagram post. | our own scheduler (Celery beat) |
| Graph API versions | New versions ship regularly (v25.0 was announced Feb 2026). | configurable version |

## What can be implemented exactly as requested

- AI-generated captions/images, templates, human approval, calendar, recurring "every N days" schedules. These are all our own application logic.
- Publishing single-image feed posts through the official API at the scheduled time.
- Checking publish status, reading back the permalink, likes and comment counts of our own posts.
- Google Sheets import/export via Google's official Sheets API with a service account.

## What requires Meta approval or configuration

- A Meta app, a professional Instagram account, and (in Development mode) an Instagram Tester role for the account.
- **App Review + Business Verification** only if accounts *without* a role on your app will connect (e.g. offering this to other companies). Not needed for the company's own account.
- A public https domain (OAuth redirect and image hosting).

## What cannot be done through the official API (and the compliant alternative)

| Wish | Status | Compliant alternative |
|---|---|---|
| Log in with the Instagram username/password, Selenium/Playwright automation, private APIs | Forbidden by Meta's terms and fragile | Official OAuth + Graph API (implemented) |
| Native "schedule on Instagram's side" through the API | Not offered by the publishing API | Our scheduler publishes at the chosen time (implemented) |
| Automatically downloading/scraping competitors' posts from Instagram or websites | Violates platform terms | Human-recorded observations and CSV import (implemented). Optional future: Meta's **Business Discovery** API returns basic public metrics and media of *other business accounts* when using the Facebook Login variant. |
| Copying competitor captions/images | Copyright / terms risk | Store your own summaries; the AI extracts high-level patterns only |
| Personal (non-professional) Instagram accounts | Not supported by the API | Switch to a free professional account |
| Non-JPEG images (PNG/WebP) | Not accepted for image posts | Automatic conversion to JPEG (implemented) |
| Posting WhatsApp *Status* updates (Phase 2) | Not part of the official WhatsApp Business Platform (Cloud API) as far as current docs show. Re-verify before Phase 2. | Opt-in broadcast template messages; a chatbot via Cloud API webhooks |
| Paid ads (future) | Possible via the separate **Marketing API** (needs its own permissions/review) | Future module |

## Sources

- Publish content: <https://developers.facebook.com/docs/instagram-platform/content-publishing/>
- IG User Media: <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/>
- Media Publish: <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media_publish/>
- Content Publishing Limit: <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit/>
- IG Container: <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-container/>
- Business Login for Instagram: <https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login/>
- OAuth Authorize: <https://developers.facebook.com/docs/instagram-platform/reference/oauth-authorize/>
- Access Token (long-lived / refresh): <https://developers.facebook.com/docs/instagram-platform/reference/access_token/>
- Business Discovery: <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/business_discovery/>
- Graph API versions: <https://developers.facebook.com/docs/graph-api/changelog/versions/>
- WhatsApp Business Platform overview: <https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform>
