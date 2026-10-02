# n8n integration (optional)

[n8n](https://n8n.io) is a visual workflow tool. It is optional; the app works fully without it. Use it to connect the content platform to the rest of the company's tools (Slack, email, Telegram, Google Forms, CRMs…) without writing code.

```
            ┌──────────── API key (X-API-Key) ───────────┐
            │  create drafts, read posts, dashboard…     ▼
         n8n  ◀──── signed webhooks ────  Instagram Automation (FastAPI)
  (forms, Slack,     post.needs_review,        │  approval, scheduling and
   email, CRM…)      post.published, …         │  Instagram publishing stay here
                                               ▼
                                         Meta Instagram API
```

**What stays in the app:** human approval, scheduling, duplicate-post protection and Instagram publishing. n8n is *not* given an admin key. With the recommended **editor** key it can create and generate drafts, but it cannot approve or publish.

---

## 1. Start n8n

n8n is an optional Docker Compose profile:

```bash
# add to .env (generate once and keep it - it encrypts credentials stored in n8n):
#   N8N_ENCRYPTION_KEY=<python -c "import secrets; print(secrets.token_hex(24))">
docker compose --profile n8n up -d
```

Open **http://localhost:5678** and create the n8n owner account. This is a separate login from the content dashboard.

Plain `docker compose up` (without `--profile n8n`) does not start n8n.

## 2. Create an API key for n8n (n8n → app)

1. Dashboard → **Settings → Automation (n8n)** → **New API key**. Use the name `n8n` and the role **editor**.
2. Copy the key (`ia_…`). It is shown only once; only a hash is stored.
3. In n8n: **Credentials → Create credential → Header Auth**:
   - Credential name: `Instagram Automation API key`
   - Name: `X-API-Key`
   - Value: the key from step 2

Inside Docker Compose, n8n reaches the API at `http://api:8000/api` (also available to workflows as `$env.IA_API_URL`).

## 3. Create a webhook to n8n (app → n8n)

1. Dashboard → **Settings → Automation (n8n)** → **New webhook**:
   - URL: `http://n8n:5678/webhook/instagram-events` (the example workflow's path)
   - Events: all, or pick the ones you need
2. Copy the **signing secret** (`whsec_…`, shown once) into `.env`:
   ```
   IA_WEBHOOK_SECRET=whsec_...
   ```
3. Run `docker compose --profile n8n up -d` again so n8n picks up the secret.

## 4. Import the example workflows

In n8n: **Workflows → ⋯ → Import from file**, and pick the files in [`../n8n/workflows/`](../n8n/workflows/):

| File | What it does |
|---|---|
| `01-receive-events.json` | Receives events from the app, **verifies the HMAC signature**, and builds a readable message (e.g. "📝 Needs review: "Exam tips" (⚠ 2 item(s) to verify)" plus a dashboard link). Replace the last node with Slack / Gmail / Telegram / WhatsApp to get notified. |
| `02-request-post-form.json` | A web form (topic, category, audience, important info, CTA). Submitting it creates a draft in the app and generates it with AI. It lands in **Needs review** for a human. |
| `03-daily-digest.json` | Every day at 09:00, builds a summary (pending approval, scheduled, failed, Instagram connection) from `GET /api/dashboard`. Replace the last node to send it somewhere. |

After importing: open each workflow, select the `Instagram Automation API key` credential on the HTTP Request nodes if n8n asks, then switch the workflow **Active / Publish**.

Alternatively, from the command line:

```bash
docker compose exec n8n n8n import:workflow --separate --input=/workflows
docker compose exec n8n n8n publish:workflow --id=iaWorkflow00001
docker compose exec n8n n8n publish:workflow --id=iaWorkflow00002
docker compose exec n8n n8n publish:workflow --id=iaWorkflow00003
docker compose restart n8n
```

## 5. Test it

- Dashboard → Settings → Automation → **Send test** next to the webhook. You should see "Test event delivered (HTTP 200)". The example workflow only answers 200 after the signature check passes, so a wrong `IA_WEBHOOK_SECRET` shows up here as a failed delivery.
- Open the form URL shown on the form trigger node (e.g. `http://localhost:5678/form/<id>`), submit it, and the new post appears in the dashboard under **Needs review**, created by "API key: n8n".

---

## Webhook reference

Every webhook is an HTTP `POST` with a JSON body:

```json
{
  "id": "4f0c…",                       // delivery id - use it to ignore duplicates
  "event": "post.published",
  "created_at": "2026-10-02T12:30:00+00:00",
  "data": {
    "post": {
      "id": 42, "status": "PUBLISHED", "category": "EXAM", "topic": "…", "headline": "…",
      "caption": "…", "hashtags": ["…"], "image_url": "https://…/media/posts/….jpg",
      "desired_publish_at": null, "scheduled_at": "…", "published_at": "…",
      "instagram_media_id": "…", "instagram_permalink": "https://www.instagram.com/p/…",
      "published_via_mock": false, "review_flags": 0, "last_error": "",
      "dashboard_url": "https://social.yourcompany.com/posts/42"
    },
    "message": "…"
  }
}
```

Headers:

| Header | Meaning |
|---|---|
| `X-IA-Event` | Event name |
| `X-IA-Delivery` | Unique delivery id (the same id is reused when a delivery is retried) |
| `X-IA-Timestamp` | Unix time (seconds) when sent |
| `X-IA-Signature` | `sha256=` + hex HMAC-SHA256 of `"<timestamp>.<raw body>"` using the signing secret |

Verify by recomputing the HMAC and rejecting requests older than 5 minutes (the example workflow's Code node does exactly this).

### Events

| Event | When |
|---|---|
| `post.created` | A post was created (dashboard, API/n8n, Google Sheets, recurring schedule) |
| `post.needs_review` | A post waits for human approval |
| `post.approved` / `post.rejected` | Review decision |
| `post.scheduled` | An approved post was scheduled or rescheduled |
| `post.published` | Published. `published_via_mock: true` means simulated (mock mode) |
| `post.publish_retry` | Temporary Instagram error; an automatic retry is scheduled |
| `post.failed` | Publishing failed permanently |
| `post.generation_failed` | AI text generation failed |
| `schedule.missed_slot` | A recurring slot passed without an approved post (nothing was published) |
| `instagram.token_expired` | The Instagram connection must be reconnected |
| `webhook.test` | Sent by the "Send test" button |

### Delivery guarantees

- Events are stored in the database **in the same transaction** as the change that caused them (an "outbox"). If n8n is down nothing is lost, and if a change is rolled back no event is sent.
- The worker sends pending events every 15 seconds. On failure (non-2xx, timeout) it retries after 30 s, 2 min, 10 min, 30 min and 1 h, then marks the delivery `failed`. Everything is visible under **Recent deliveries**.
- Delivery is *at least once*: use `X-IA-Delivery` to ignore an occasional duplicate.
- Delivery logs older than 30 days are deleted automatically.

## Useful API calls from n8n

All require the `X-API-Key` header. Full list: [API.md](API.md) or http://localhost:8000/docs.

| Goal | Request |
|---|---|
| Create + AI-generate a draft | `POST /api/posts` `{"topic": "...", "category_id": 4, "important_info": "...", "cta": "...", "generate": true}` |
| List posts waiting for review | `GET /api/posts?status=NEEDS_REVIEW` |
| Get one post | `GET /api/posts/{id}` |
| Generate content ideas | `POST /api/ideas/generate` `{"count": 5, "theme": "board exams"}` |
| Dashboard numbers | `GET /api/dashboard` |
| Category ids | `GET /api/categories` |
| Trigger a Google Sheets sync | `POST /api/sheets/sync` (needs an **approver** key) |

## Security notes

- API keys can be **viewer**, **editor** or **approver**, never admin. An approver key lets automation approve and publish, which bypasses the human review, so only use one deliberately.
- Revoke a key at any time (Settings → Automation → Revoke); it stops working immediately.
- Keys and webhook secrets are shown once. Keys are stored only as a SHA-256 hash; webhook secrets are encrypted.
- In production, serve n8n over HTTPS behind your reverse proxy, set `N8N_SECURE_COOKIE=true` and `N8N_PUBLIC_URL=https://n8n.yourcompany.com/`, and don't expose port 5678 publicly without it.
- Webhook URLs can point to internal addresses (e.g. `http://n8n:5678`). Only admins can create webhooks.

## Phase 2 ideas with n8n

- WhatsApp lead → n8n → CRM / Google Sheet → notify the sales team.
- `post.published` → n8n → share the Instagram link in a WhatsApp/Telegram group.
- Form or email request → n8n → draft post (already included as example 2).
