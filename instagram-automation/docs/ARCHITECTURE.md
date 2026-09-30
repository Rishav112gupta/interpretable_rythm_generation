# Architecture

```
                         ┌──────────────────────────────┐
   Browser ─────────────▶│ frontend (nginx)  :8080      │  React + TypeScript + Vite + Tailwind
                         │  /        → SPA              │
                         │  /api/*   → api:8000         │
                         │  /media/* → api:8000         │
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │ api (FastAPI)                │  auth, validation, workflow,
                         │                              │  generation on request
                         └───┬──────────┬───────────┬───┘
                             │          │           │
                   ┌─────────▼──┐  ┌────▼─────┐  ┌──▼──────────────────────────┐
                   │ PostgreSQL │  │  Redis   │  │ Provider abstractions       │
                   │ (truth)    │  │ (queue)  │  │  LLM: anthropic/openai/mock │
                   └─────▲──────┘  └────▲─────┘  │  Image: openai/none/mock    │
                         │              │        │  Instagram: graph/mock      │
                   ┌─────┴──────────────┴─────┐  │  Sheets: gspread/mock       │
                   │ worker (Celery)          │──│  Storage: local/S3          │
                   │ beat   (Celery, 1 only)  │  └──────────────┬──────────────┘
                   └──────────────────────────┘                 │
                                                  Meta Graph API · Google Sheets API
                                                  LLM API · Image API · S3
```

## Why this stack

| Choice | Reason |
|---|---|
| **FastAPI** | Typed request validation (Pydantic), automatic API docs, simple to deploy. |
| **PostgreSQL** | Single source of truth, transactions (needed for the atomic "claim to publish" step), time-zone aware timestamps. |
| **Celery + Redis** | Publishing must happen when nobody has the dashboard open and must survive restarts. Beat fires small periodic "ticks" and the *database* holds the schedule, so a Redis restart loses nothing. |
| **Pillow templates as JSON** | Designs are data, not code. New templates can be added from the dashboard, and output is always an Instagram-valid JPEG. |
| **Provider interfaces + mocks** | The whole system runs and is tested without credentials; switching providers is an `.env` change. |

## Folder structure

```
instagram-automation/
├── backend/
│   ├── app/
│   │   ├── api/            deps.py (auth/roles/rate limits), routes/*.py
│   │   ├── core/           config, security (JWT, bcrypt, Fernet), log redaction, errors, rate limiting
│   │   ├── database/       SQLAlchemy engine/session
│   │   ├── models/         ORM models + enums (statuses, roles)
│   │   ├── schemas/        request/response validation
│   │   ├── scheduler/      Celery app + periodic tasks
│   │   ├── services/
│   │   │   ├── ai/                 LLMProvider, anthropic/openai/mock, prompts, output schemas, fact guard
│   │   │   ├── image_generation/   ImageProvider, openai/none/mock
│   │   │   ├── templates/          JSON layout renderer + built-in templates/categories
│   │   │   ├── storage/            local disk / S3
│   │   │   ├── instagram/          Graph API client, mock client, account/OAuth, publisher
│   │   │   ├── google_sheets/      sync (export + import)
│   │   │   ├── competitors/        observation import + AI insights
│   │   │   ├── content/            generation pipeline, approval workflow, ideas, audit log
│   │   │   ├── scheduling/         recurrence math, planner
│   │   │   └── channels/           publishing-channel interface (Phase 2 extension point)
│   │   ├── main.py         FastAPI app
│   │   └── seed.py         default templates/categories/admin
│   ├── alembic/            database migrations
│   └── tests/              pytest suite (all external services mocked)
├── frontend/src/           components/, pages/ (+ settings/), services/api.ts, hooks/, types/, utils/
├── docker/                 production compose override
├── docs/                   this documentation
├── docker-compose.yml
└── .env.example
```

## Post lifecycle

```
DRAFT ──generate──▶ AI_GENERATED ──▶ NEEDS_REVIEW ──approve──▶ APPROVED ──schedule──▶ SCHEDULED
  ▲                                     │   ▲                     │                       │
  │                                  reject │ edit after approval │                  (time arrives)
  │                                     ▼   │                     ▼                       ▼
  └──────────── edit/regenerate ──── REJECTED                 publish now ───────▶ PUBLISHING
                                                                                  │    │    │
                                                                  temporary error ┘    │    └ permanent error
                                                                (retry 1/5/15 min)     ▼              ▼
                                                                                   PUBLISHED        FAILED
```

- Only `APPROVED`/`SCHEDULED` posts can be published. Editing an approved post sends it back to review.
- `PUBLISHING` is an internal lock state (see below).
- Every transition is written to `post_events` (the History panel).

## Duplicate-post prevention

1. **Atomic claim:** `UPDATE posts SET status='PUBLISHING' WHERE id=? AND status IN (…) AND instagram_media_id IS NULL`. Only one worker or request can win.
2. **Container first:** the Instagram container id is committed *before* `media_publish` is called. Every retry first asks Instagram for the container's status. If it is already `PUBLISHED` (for example the response was lost), the post is recorded as published and not sent again.
3. `instagram_media_id` is `UNIQUE`, and posts with one can never be claimed.
4. **Crash recovery:** posts stuck in `PUBLISHING` for 15 minutes go back to the queue; step 2 makes that safe.
5. If the database write fails *after* Instagram accepted the post, the post is queued for a retry that goes through step 2 (covered by a regression test).

## "AI must never invent facts"

1. The system prompt forbids inventing prices, dates, claims, statistics, testimonials or contacts, and asks for `missing_information` instead.
2. Only the brand profile's **verified facts** and the post's own input count as sources.
3. After generation, a **fact guard** scans the text for prices, percentages, dates, phone numbers, emails, links, discounts, guarantees, numeric claims, quotes and `[PLACEHOLDERS]`. Anything not found in the verified sources becomes a **review flag**.
4. Approval is blocked until the approver ticks "I have checked the flagged items".

## Two scheduling clocks

- **A. Content generation:** the planner creates a draft for each upcoming slot of a recurring schedule (14 days ahead). `generation_lead_hours` before the slot the AI generates it into `NEEDS_REVIEW`.
- **B. Publishing:** every minute the worker publishes `SCHEDULED` posts whose time has arrived. A slot whose post was never approved is **not** published; a "missed slot" warning is logged instead.

All times are stored in UTC and displayed in the configurable company timezone (default Asia/Kolkata).

## Security

- All secrets come from environment variables; `.env` is git-ignored.
- Instagram tokens are Fernet-encrypted in the database and never returned by any endpoint.
- Passwords are hashed with bcrypt. Sessions use signed JWTs (12 h), and there are four roles.
- The login and AI-generation endpoints are rate-limited.
- Logs pass through a redaction filter (`access_token=…`, `Bearer …`, API-key patterns). HTTP client loggers that print URLs are silenced.
- The production start refuses default `SECRET_KEY`, a missing `TOKEN_ENCRYPTION_KEY` or a localhost `PUBLIC_BASE_URL`.
- Media files are public on purpose (Instagram must download them), with unguessable UUID names.

## Phase 2 (WhatsApp) readiness, not implemented

```
Instagram ─▶ audience ─▶ lead ─▶ WhatsApp (Cloud API webhooks) ─▶ chatbot ─▶ qualification ─▶ Sheets/CRM
```

The extension points already in place:

- `posts.channel` column plus `services/channels` (`PublishingChannel` interface). A `WhatsAppChannel` can be added next to `InstagramChannel`, and the approval workflow and scheduler work unchanged.
- LLM provider abstraction: the same providers can power a chatbot.
- `IntegrationLog`, roles and the Sheets sync are channel-agnostic.

Suggested Phase 2 additions: `leads` and `conversations` tables, a `/webhooks/whatsapp` endpoint with signature verification, a lead-qualification service using the LLM layer, and a Sheets/CRM export for leads. Re-verify WhatsApp Status capabilities before building. See [META_API_RESEARCH.md](META_API_RESEARCH.md).
