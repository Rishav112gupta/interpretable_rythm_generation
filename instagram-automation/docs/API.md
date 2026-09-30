# API reference

The backend is a FastAPI application. Interactive documentation (try requests in the browser) is generated automatically from the code:

- Swagger UI: **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**
- Machine-readable spec: [`openapi.json`](openapi.json) (exported from the running server)

## Authentication

1. `POST /api/auth/login` with `{"email": "...", "password": "..."}` → `{"access_token": "...", "user": {...}}`
2. Send `Authorization: Bearer <access_token>` on every other request.

Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 12 hours). Login is rate-limited per IP.

### Roles

| Role | Can do |
|---|---|
| `viewer` | Read everything |
| `editor` | + create, generate, edit posts; ideas; competitor observations |
| `approver` | + approve, reject, schedule, publish, delete posts; recurring schedules; Sheets sync |
| `admin` | + users, settings, brand profile, categories, templates, Instagram connection |

## Errors

Errors are JSON: `{"error": "<code>", "detail": "<human readable message>", "details": {...}}`.

| HTTP | `error` | Meaning |
|---|---|---|
| 401 | – | Not logged in / session expired |
| 403 | – | Your role is not allowed to do this |
| 404 | `not_found` | Unknown id |
| 409 | `invalid_status_transition` | E.g. approving a post that is not awaiting review |
| 409 | `duplicate_publish` | The post was already published (it will not be posted twice) |
| 422 | `validation_failed` | Invalid input, or approval blocked by unacknowledged review flags |
| 429 | `rate_limited` | Too many requests |
| 502 | `llm_error`, `image_generation_error`, `instagram_api_error`, `google_sheets_error` | An external service failed (`transient: true` means retrying may help) |
| 503 | `database_error` | Database problem |

## Post lifecycle endpoints

```
POST /api/posts                    create (optionally "generate": true)
POST /api/posts/{id}/generate      AI text + image          DRAFT/REJECTED -> NEEDS_REVIEW
POST /api/posts/{id}/regenerate-text   {"feedback": "..."}
POST /api/posts/{id}/regenerate-image
POST /api/posts/{id}/image         multipart upload (replace image)
PATCH /api/posts/{id}              edit (editing an approved post -> NEEDS_REVIEW)
POST /api/posts/{id}/submit        manual draft -> NEEDS_REVIEW
POST /api/posts/{id}/approve       {"acknowledge_flags": true, "schedule_at": "2026-10-01T12:30:00Z"}
POST /api/posts/{id}/reject        {"reason": "..."}
POST /api/posts/{id}/schedule      {"scheduled_at": "<ISO 8601 with timezone>"}
POST /api/posts/{id}/unschedule
POST /api/posts/{id}/publish       publish an approved post now
```

All datetimes are ISO 8601 **with a timezone offset** (naive datetimes are rejected). Responses are in UTC.

## All endpoints

### auth

| Method | Path | Summary |
|---|---|---|
| GET | `/api/auth/me` | Me |
| GET | `/api/users` | List Users |
| PATCH | `/api/users/{user_id}` | Update User |
| POST | `/api/auth/change-password` | Change Password |
| POST | `/api/auth/login` | Login |
| POST | `/api/users` | Create User |

### brand

| Method | Path | Summary |
|---|---|---|
| GET | `/api/brand` | Read Brand |
| POST | `/api/brand/logo` | Upload Logo |
| PUT | `/api/brand` | Update Brand |

### categories

| Method | Path | Summary |
|---|---|---|
| GET | `/api/categories` | List Categories |
| PATCH | `/api/categories/{cat_id}` | Update Category |
| POST | `/api/categories` | Create Category |

### competitors

| Method | Path | Summary |
|---|---|---|
| DELETE | `/api/competitors/{cid}` | Delete Competitor |
| DELETE | `/api/observations/{oid}` | Delete Observation |
| GET | `/api/competitors` | List Competitors |
| GET | `/api/competitors/{cid}/observations` | List Observations |
| GET | `/api/insights` | List Insights |
| POST | `/api/competitors` | Create Competitor |
| POST | `/api/competitors/analyze` | Analyze |
| POST | `/api/competitors/import` | Import Csv |
| POST | `/api/competitors/{cid}/observations` | Add Observation |
| POST | `/api/insights/{iid}/toggle` | Toggle Insight |
| PUT | `/api/competitors/{cid}` | Update Competitor |

### dashboard

| Method | Path | Summary |
|---|---|---|
| GET | `/api/dashboard` | Dashboard |

### google-sheets

| Method | Path | Summary |
|---|---|---|
| GET | `/api/sheets/preview` | Sheets Preview |
| GET | `/api/sheets/status` | Sheets Status |
| POST | `/api/sheets/sync` | Sheets Sync |

### health

| Method | Path | Summary |
|---|---|---|
| GET | `/api/health` | Health |

### ideas

| Method | Path | Summary |
|---|---|---|
| GET | `/api/ideas` | List Ideas |
| POST | `/api/ideas/generate` | Generate Ideas |
| POST | `/api/ideas/{idea_id}/convert` | Convert Idea |
| POST | `/api/ideas/{idea_id}/dismiss` | Dismiss Idea |

### instagram

| Method | Path | Summary |
|---|---|---|
| GET | `/api/instagram/oauth/start` | Oauth Start |
| GET | `/api/instagram/status` | Instagram Status |
| POST | `/api/instagram/disconnect` | Disconnect |
| POST | `/api/instagram/refresh-token` | Refresh Token |
| POST | `/api/instagram/test` | Test Connection |

### posts

| Method | Path | Summary |
|---|---|---|
| DELETE | `/api/posts/{post_id}` | Delete Post |
| GET | `/api/posts` | List Posts |
| GET | `/api/posts/calendar` | Calendar |
| GET | `/api/posts/{post_id}` | Get Post |
| PATCH | `/api/posts/{post_id}` | Update Post |
| POST | `/api/posts` | Create Post |
| POST | `/api/posts/{post_id}/approve` | Approve |
| POST | `/api/posts/{post_id}/generate` | Generate |
| POST | `/api/posts/{post_id}/image` | Upload Image |
| POST | `/api/posts/{post_id}/publish` | Publish Now |
| POST | `/api/posts/{post_id}/regenerate-image` | Regenerate Image |
| POST | `/api/posts/{post_id}/regenerate-text` | Regenerate Text |
| POST | `/api/posts/{post_id}/reject` | Reject |
| POST | `/api/posts/{post_id}/schedule` | Schedule |
| POST | `/api/posts/{post_id}/submit` | Submit For Review |
| POST | `/api/posts/{post_id}/unschedule` | Unschedule |

### schedules

| Method | Path | Summary |
|---|---|---|
| DELETE | `/api/schedules/{schedule_id}` | Delete Schedule |
| GET | `/api/schedules` | List Schedules |
| POST | `/api/schedules` | Create Schedule |
| POST | `/api/schedules/preview` | Preview Schedule |
| POST | `/api/schedules/run` | Run Planner |
| PUT | `/api/schedules/{schedule_id}` | Update Schedule |

### settings

| Method | Path | Summary |
|---|---|---|
| GET | `/api/logs` | List Logs |
| GET | `/api/settings` | Get App Settings |
| PATCH | `/api/settings` | Update App Settings |

### templates

| Method | Path | Summary |
|---|---|---|
| GET | `/api/templates` | List Templates |
| GET | `/api/templates/{template_id}/preview` | Preview Template |
| PATCH | `/api/templates/{template_id}` | Update Template |
| POST | `/api/templates` | Create Template |
