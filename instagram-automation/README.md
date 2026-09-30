# Instagram Automation: AI-assisted content platform (Phase 1)

A web application that helps a company plan, write, design, approve, schedule and publish Instagram posts, using AI for the drafting and the **official Meta Instagram API** for publishing. A human always approves before anything goes live.

```
Company info → content plan → category/topic → AI text → AI image → template design
            → HUMAN APPROVAL → schedule → official Instagram API → post → logs & analytics
```

> **Status:** The complete application is implemented and tested, including the real Instagram Graph API integration. By default it runs in **mock mode**: AI, images, Instagram and Google Sheets are simulated, so you can try everything without any accounts. **Real Instagram publishing still requires Meta configuration and credentials.** Follow [docs/INSTAGRAM_SETUP.md](docs/INSTAGRAM_SETUP.md). Until then, "published" posts are clearly labelled *simulated* and nothing is posted to Instagram.

| Dashboard | Review screen |
|---|---|
| ![Dashboard](docs/images/dashboard.jpg) | ![Post review](docs/images/post-review.jpg) |
| **Content calendar** | **"Every 4th day" schedule** |
| ![Calendar](docs/images/calendar.jpg) | ![Schedule](docs/images/schedule.jpg) |

---

## Contents

1. [What the project does](#1-what-the-project-does)
2. [Architecture](#2-architecture)
3. [Folder structure](#3-folder-structure)
4. [Prerequisites](#4-prerequisites)
5. [Installation](#5-installation)
6. [Environment variables](#6-environment-variables)
7. [Database setup](#7-database-setup)
8. [Running locally](#8-running-locally)
9. [Running tests](#9-running-tests)
10. [Setting up Google Sheets](#10-setting-up-google-sheets)
11. [Setting up the LLM provider](#11-setting-up-the-llm-provider)
12. [Setting up image generation](#12-setting-up-image-generation)
13. [Setting up the Meta/Instagram API](#13-setting-up-the-metainstagram-api)
14. [Connecting Instagram](#14-connecting-instagram)
15. [Scheduling posts](#15-scheduling-posts)
16. [Deployment](#16-deployment)
17. [Troubleshooting](#17-troubleshooting)

More documents: [Architecture](docs/ARCHITECTURE.md) · [API reference](docs/API.md) · [Instagram setup](docs/INSTAGRAM_SETUP.md) · [Meta API research: what is and isn't possible](docs/META_API_RESEARCH.md) · [Deployment](docs/DEPLOYMENT.md)

---

## 1. What the project does

| Feature | Details |
|---|---|
| **Create post** | Form with category, topic, audience, tone, objective, important info, CTA, language, brand instructions, reference material, image instructions, desired date/time. **Generate with AI** produces headline, subtitle, caption, alternative caption, CTA, hashtags, image prompt and summary as validated JSON. |
| **AI image + templates** | An image is generated from the prompt, then placed in a design template (logo, headline, CTA, brand colours) and exported as an Instagram-ready 1080×1350 JPEG. Seven templates are built in (Announcement, Exam, Promotional, Educational, Batch, Quote, Event); templates are JSON and editable in the dashboard. |
| **Human approval** | `DRAFT → AI_GENERATED → NEEDS_REVIEW → APPROVED → SCHEDULED → PUBLISHED`, plus `REJECTED` and `FAILED`. Edit caption, headline and hashtags; replace or regenerate the image; regenerate the text with feedback; approve, reject, schedule or publish now. Editing an approved post requires re-approval. |
| **No invented facts** | Brand profile with a *verified facts* list. The AI may only state prices, dates, course details, claims and contacts given there or in the post input. A fact guard flags anything else, and approval requires ticking "I verified the flagged items". |
| **Scheduling** | Specific date/time, or recurring schedules such as **every 4th day at 18:00** (two interpretations: rolling every N days, or days N, 2N, 3N… of each month). Content generation happens ahead of time (configurable), separately from publishing. Timezone-aware (default Asia/Kolkata, changeable). |
| **Publishing** | Official Instagram Graph API container → status → publish flow, with retries after 1, 5 and 15 minutes for temporary errors, and multiple layers of **duplicate-post prevention**. |
| **Categories** | NORMAL, BATCH, CLASS_SPECIFIC, EXAM, IMPORTANT, PROMOTIONAL, RANDOM. Admins can add, edit and deactivate them. |
| **Content ideas** | "Generate content ideas" produces a batch (tips, myth vs fact, FAQ…); turn any idea into a post in one click. |
| **Competitor research** | Record (or CSV-import) observations of competitor content in your own words. The AI extracts high-level patterns (topics, gaps, CTAs, visual trends) that feed original content. No scraping, no copying. |
| **Google Sheets** | Optional two-way control layer: new topic rows become drafts; every post's status, caption, schedule and Instagram URL is written back. PostgreSQL stays the source of truth. |
| **Dashboard & calendar** | Counts by status, next scheduled post, upcoming/planned posts, recent errors, Instagram connection status; month calendar coloured by status. |
| **Security** | Login with roles (admin/approver/editor/viewer), encrypted tokens, secret redaction in logs, rate limits, input validation, secrets only in `.env`. |
| **Phase 2 ready** | The channel abstraction and LLM layer are prepared for WhatsApp (not implemented). See [ARCHITECTURE.md](docs/ARCHITECTURE.md#phase-2-whatsapp-readiness-not-implemented). |

## 2. Architecture

```
            React dashboard (nginx :8080)
                        │  /api, /media
                FastAPI backend (:8000) ─────────── PostgreSQL (source of truth)
                  │           │                 └── Redis (job queue)
       ┌──────────┼───────────┼────────────────┐
   LLM provider  Image provider  Template renderer  Storage (disk / S3)
       │
 Celery worker + beat ──▶ Instagram service ──▶ Meta Graph API ──▶ Instagram
       │                  Google Sheets sync ◀─▶ Google Sheets
       └ competitor observations → AI insights → content strategy → LLM
```

Every external service sits behind an interface with a **mock implementation**, so the app works without credentials and tests never touch real services. Full details, design decisions, duplicate-prevention and the Phase 2 plan are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Stack:** React 19 + TypeScript + Vite + Tailwind CSS 4 · Python 3.11 + FastAPI + SQLAlchemy 2 + Alembic · PostgreSQL 16 · Celery + Redis · Pillow · Docker Compose.

## 3. Folder structure

```
instagram-automation/
├── backend/
│   ├── app/
│   │   ├── api/routes/        HTTP endpoints (auth, posts, planning, integrations, config)
│   │   ├── core/              settings, security, logging redaction, errors, rate limits
│   │   ├── database/          DB session
│   │   ├── models/            database tables
│   │   ├── schemas/           input/output validation
│   │   ├── scheduler/         Celery worker & periodic tasks
│   │   └── services/          ai/, image_generation/, templates/, storage/, instagram/,
│   │                          google_sheets/, competitors/, content/, scheduling/, channels/
│   ├── alembic/               database migrations
│   ├── tests/                 104 automated tests
│   ├── Dockerfile  requirements.txt  requirements-dev.txt
├── frontend/
│   ├── src/                   components/ pages/ services/ hooks/ types/ utils/
│   ├── Dockerfile  nginx.conf
├── docker/docker-compose.prod.yml
├── docs/                      architecture, API, Instagram setup, deployment, research
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## 4. Prerequisites

To just run it (recommended):

- **Docker Desktop** (Windows/Mac) or Docker Engine + Compose v2 (Linux): <https://docs.docker.com/get-docker/>

To develop without Docker (optional): Python 3.11+, Node.js 20+, PostgreSQL 14+, Redis 6+.

External accounts are **only** needed when you switch off the mocks: an LLM API key, an image API key, a Meta developer app with an Instagram Professional account, and a Google Cloud service account.

## 5. Installation

```bash
git clone <this repository>
cd <repository>/instagram-automation
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

Open `.env` in a text editor and set at least:

```
FIRST_ADMIN_EMAIL=you@yourcompany.com
FIRST_ADMIN_PASSWORD=<a password you choose>
SECRET_KEY=<any long random text, 32+ characters>
```

Everything else can stay as it is for a first run (all mocks on).

## 6. Environment variables

All configuration is in `.env` (template: [`.env.example`](.env.example), with comments for every line). Never commit `.env`; it is git-ignored.

| Group | Variables | Notes |
|---|---|---|
| General | `APP_ENV`, `SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, `PUBLIC_BASE_URL`, `FRONTEND_URL`, `CORS_ORIGINS`, `DEFAULT_TIMEZONE`, `LOG_LEVEL`, `ACCESS_TOKEN_EXPIRE_MINUTES` | Production refuses to start with a weak `SECRET_KEY`, without `TOKEN_ENCRYPTION_KEY`, or with a localhost `PUBLIC_BASE_URL`. |
| First admin | `FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD` | Used only when the users table is empty. If the password is empty, a random one is printed once in the API log. |
| Database/queue | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (Docker) · `DATABASE_URL`, `REDIS_URL` (without Docker) | |
| Mocks | `MOCK_LLM`, `MOCK_IMAGE_GENERATION`, `MOCK_INSTAGRAM`, `MOCK_GOOGLE_SHEETS` | `true` = simulated; overrides the provider settings. |
| LLM | `LLM_PROVIDER` (`anthropic`/`openai`/`mock`), `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS` | See §11. |
| Images | `IMAGE_PROVIDER` (`openai`/`none`/`mock`), `IMAGE_API_KEY`, `IMAGE_MODEL`, `IMAGE_BASE_URL` | See §12. |
| Storage | `STORAGE_BACKEND` (`local`/`s3`), `MEDIA_ROOT`, `S3_*` | Images must be publicly reachable for Instagram. |
| Meta | `META_LOGIN_TYPE`, `META_GRAPH_API_VERSION`, `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`, `META_OAUTH_SCOPES`, `META_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID` | See §13–14. |
| Publishing | `PUBLISHING_ENABLED`, `PUBLISH_RETRY_DELAYS` | Default retries after 60, 300, 900 seconds. |
| Google Sheets | `GOOGLE_SHEETS_ENABLED`, `GOOGLE_SERVICE_ACCOUNT_FILE` or `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_WORKSHEET` | See §10. A service account is used instead of an OAuth client ID/secret because the server syncs on its own, without a person logging in. |
| Rate limits | `LOGIN_RATE_LIMIT_PER_MINUTE`, `GENERATION_RATE_LIMIT_PER_MINUTE` | |

## 7. Database setup

With Docker there is nothing to do: the `api` container runs `alembic upgrade head` (creates or updates all tables) on every start, then seeds the default templates, categories, empty brand profile and first admin.

Without Docker:

```bash
createdb insta                         # or use any PostgreSQL database
cd backend
export DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/insta
alembic upgrade head
python -m app.seed
```

## 8. Running locally

### With Docker (recommended)

```bash
docker compose up --build
```

- Dashboard: **http://localhost:8080** (log in with `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD`)
- API docs: **http://localhost:8000/docs**

Stop with `Ctrl+C` or `docker compose down`. Data is kept in Docker volumes; `docker compose down -v` deletes it.

Services: `db` (PostgreSQL), `redis`, `api` (FastAPI), `worker` (publishing and generation jobs), `beat` (timer that triggers jobs every minute), `frontend` (nginx serving the dashboard).

**Try the full flow in mock mode:** Settings → Brand profile (company name and a verified fact) → Create post → Generate with AI → review the flags → Approve (tick the confirmation) with a time → Publish now → see "Published (simulated)". Then try Recurring schedules → New schedule (every 4 days) → Run planner now.

### Without Docker (for development)

```bash
# terminal 1 - backend API
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# terminal 2 - background worker + timer (needs Redis running)
cd backend && source .venv/bin/activate
celery -A app.scheduler.celery_app worker -B --loglevel=INFO

# terminal 3 - frontend (proxies /api to :8000)
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Settings are read from `backend/.env` or `instagram-automation/.env`.

## 9. Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                         # 104 tests, SQLite, ~25 s
TEST_DATABASE_URL=postgresql+psycopg://insta:insta@localhost:5432/insta_test pytest   # same suite on PostgreSQL
ruff check app tests           # lint

cd ../frontend
npm run build                  # type-check + production build
```

Tests never call real services and never publish to Instagram. They cover post creation, AI response parsing and validation, the fact guard, the every-4-day calculation (including DST), the recurring planner, the approval workflow, API authorisation and validation, the Instagram Graph client (fake HTTP transport: endpoints, error classification, token never leaked), publishing retries (1/5/15 min then FAILED), duplicate-publish prevention (atomic claim, lost response, crashed worker, DB failure after publish), Google Sheets sync and failures, image generation failures, competitor analysis, token encryption and log redaction.

## 10. Setting up Google Sheets

1. Go to <https://console.cloud.google.com/>, create a project, open **APIs & Services → Library** and enable **Google Sheets API**.
2. **APIs & Services → Credentials → Create credentials → Service account**. Open it, go to **Keys → Add key → JSON**, and download the file. Keep it secret.
3. Create a Google Sheet. Click **Share** and give **Editor** access to the service account's email (it looks like `name@project.iam.gserviceaccount.com`).
4. Copy the sheet ID from its URL: `https://docs.google.com/spreadsheets/d/<THIS_PART>/edit`.
5. In `.env`:
   ```
   MOCK_GOOGLE_SHEETS=false
   GOOGLE_SHEETS_ENABLED=true
   GOOGLE_SHEET_ID=<id>
   GOOGLE_SHEET_WORKSHEET=Posts
   GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/google-sa.json
   ```
   With Docker, put the JSON in `instagram-automation/secrets/google-sa.json` (git-ignored) and add `- ./secrets:/app/secrets:ro` under `volumes:` in the `x-backend` section of `docker-compose.yml`. Alternatively paste the whole JSON on one line into `GOOGLE_SERVICE_ACCOUNT_JSON`.
6. Restart, then **Settings → Google Sheets → Sync now** (optionally turn on auto-sync every 30 minutes).

Columns: `Post ID, Date, Category, Topic, Target Audience, Status, Caption, Image, Scheduled Time, Published, Instagram URL, Last Synced`. To request content from the sheet, add a row with a Category key (e.g. `EXAM`), a Topic and Status `NEW`, leaving Post ID empty; it becomes a draft on the next sync.

## 11. Setting up the LLM provider

**Anthropic Claude (default when not mocked):**

1. Create an API key at <https://console.anthropic.com/> → **API Keys**.
2. `.env`: `MOCK_LLM=false`, `LLM_PROVIDER=anthropic`, `LLM_API_KEY=<key>`. `LLM_MODEL` can stay empty (defaults to `claude-opus-5-5`).

The request uses structured JSON output, so responses always match the schema; they are validated again before saving.

**OpenAI or any OpenAI-compatible API:** `LLM_PROVIDER=openai`, `LLM_API_KEY=<key>` (<https://platform.openai.com/api-keys>), `LLM_MODEL=<model name>`, and `LLM_BASE_URL` if you use another compatible service.

Adding another provider means one new class implementing `LLMProvider.complete_json()` in `backend/app/services/ai/`. Prompts are versioned (`PROMPT_VERSION`), and each post records provider, model, prompt version, generation time and regeneration count.

## 12. Setting up image generation

- **OpenAI Images:** `MOCK_IMAGE_GENERATION=false`, `IMAGE_PROVIDER=openai`, `IMAGE_API_KEY=<key>`, `IMAGE_MODEL=gpt-image-1` (or another model your account offers).
- **No AI images:** `IMAGE_PROVIDER=none`. Posts use template-only designs or images you upload.
- Other providers: implement `ImageProvider.generate()` in `backend/app/services/image_generation/`.

The AI image is always passed through the selected template and converted to a JPEG that meets Instagram's rules (≤ 8 MB, aspect ratio 4:5 to 1.91:1). Uploaded images are validated and cropped automatically.

## 13. Setting up the Meta/Instagram API

Summary (full step-by-step guide: [docs/INSTAGRAM_SETUP.md](docs/INSTAGRAM_SETUP.md)):

1. Switch the Instagram account to a **Professional** (Business/Creator) account.
2. Create a Meta developer account and an app with the Instagram use case at <https://developers.facebook.com/>.
3. From **Instagram → API setup with Instagram login**, copy the **Instagram app ID/secret** into `META_APP_ID` / `META_APP_SECRET`.
4. Register the OAuth redirect URI `https://<your-domain>/api/instagram/oauth/callback` and set the same value in `META_REDIRECT_URI`.
5. Add the company's Instagram account as an **Instagram Tester** and accept the invite.
6. Make sure images are publicly reachable: `PUBLIC_BASE_URL=https://<your-domain>` or S3 storage.
7. Set `MOCK_INSTAGRAM=false` and `TOKEN_ENCRYPTION_KEY`, then restart.

What the official API can and can't do (for example, there is no Instagram-side scheduling, only professional accounts are supported, and the limit is 100 posts per 24 hours) is documented with sources in [docs/META_API_RESEARCH.md](docs/META_API_RESEARCH.md).

## 14. Connecting Instagram

Dashboard → **Settings → Instagram** → **Connect Instagram account** → log in to Instagram and approve → you return to the dashboard, connected. The page shows the account, connection and token status, the last successful API request, API errors, the publishing quota, and Reconnect / Test / Disconnect buttons. Tokens are encrypted, never shown in the browser, and refreshed automatically.

## 15. Scheduling posts

- **One post:** approve it and pick a date/time in the approve dialog, or later with **Schedule**. The worker publishes it within about a minute of that time.
- **Recurring ("every 4th day"):** **Recurring schedules → New schedule**. Choose what "every N days" means (rolling from a start date, or the Nth, 2Nth… day of each month), the posting time and timezone, how many hours ahead to generate content, the categories to rotate, and a topic pool (or leave it empty to let the AI suggest topics). The preview shows the exact next dates.
  - Clock A: drafts are created for slots 14 days ahead and generated `generation_lead_hours` before each slot → **Needs review**.
  - Clock B: when approved, the post is scheduled for its slot automatically and published then. **Unapproved posts are never published**; you get a "missed slot" warning instead.
- **Pause everything:** Settings → General → **Pause publishing**.
- Timezone: Settings → General (default Asia/Kolkata).

## 16. Deployment

Single-server Docker deployment with HTTPS, backups and updates: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

```bash
docker compose -f docker-compose.yml -f docker/docker-compose.prod.yml up -d --build
```

## 17. Troubleshooting

| Problem | What to do |
|---|---|
| Dashboard shows "Cannot reach the server" | `docker compose ps`: is `api` healthy? Check `docker compose logs api`. |
| Can't log in / forgot the admin password | The admin is created only when there are no users. Reset with `docker compose exec api python -c "from app.database.session import SessionLocal; from app.models import User; from app.core.security import hash_password; db=SessionLocal(); u=db.query(User).filter_by(email='admin@example.com').one(); u.hashed_password=hash_password('NEW-PASSWORD'); db.commit()"` |
| API log: "Database not ready for seeding" | The DB wasn't migrated. Run `docker compose exec api alembic upgrade head`, then restart `api`. |
| Posts stay "Scheduled" after their time | Are `worker` and `beat` running (`docker compose ps`)? Is publishing paused (red banner)? Look at the post's History and Settings → Logs. |
| "Publishing failed … localhost" | Instagram cannot download images from localhost. See [INSTAGRAM_SETUP.md, Step 7](docs/INSTAGRAM_SETUP.md#step-7-make-images-publicly-reachable). |
| "Instagram access token is invalid or expired" | Settings → Instagram → Reconnect. |
| Approve button disabled | The post has review flags: tick "I have checked the flagged items" after verifying them. |
| AI errors ("rejected the API key", "rate limit") | Check `LLM_API_KEY` / `IMAGE_API_KEY` and your provider billing. Errors are listed in Settings → Logs. |
| Google Sheets "Could not open the Google Sheet" | Check `GOOGLE_SHEET_ID` and that the sheet is shared with the service-account email. |
| Port 8080 / 8000 already in use | Change the left side of `ports:` in `docker-compose.yml` (e.g. `"9080:80"`). |
| Start-up error "Refusing to start in production…" | Set `SECRET_KEY` (32+ chars), `TOKEN_ENCRYPTION_KEY`, and a public `PUBLIC_BASE_URL`. |

Logs: `docker compose logs -f api worker beat`. Access tokens and API keys are automatically redacted.
