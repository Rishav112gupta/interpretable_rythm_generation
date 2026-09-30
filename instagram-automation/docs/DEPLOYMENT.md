# Deployment (single cloud server)

This is the simplest production setup: one Linux VM (for example 2 vCPU / 4 GB RAM on AWS Lightsail, DigitalOcean, Hetzner, Azure or GCP) running everything with Docker Compose, behind HTTPS.

## 1. Server preparation

```bash
# Ubuntu 24.04 example
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER   # log out and back in
```

Point a DNS record (for example `social.yourcompany.com`) to the server's IP address.

## 2. Get the code and configure

```bash
git clone <your repository URL> && cd <repo>/instagram-automation
cp .env.example .env
nano .env
```

Set at least:

```
APP_ENV=production
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
TOKEN_ENCRYPTION_KEY=<python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
PUBLIC_BASE_URL=https://social.yourcompany.com
FRONTEND_URL=https://social.yourcompany.com
META_REDIRECT_URI=https://social.yourcompany.com/api/instagram/oauth/callback
FIRST_ADMIN_EMAIL=you@yourcompany.com
FIRST_ADMIN_PASSWORD=<strong password, change after first login>
POSTGRES_PASSWORD=<strong password>
```

Then add the provider keys (LLM, image, Meta, Google) and turn off the mocks you have credentials for.

> Keep `TOKEN_ENCRYPTION_KEY` safe and unchanged. If it changes, stored Instagram tokens cannot be decrypted and you must reconnect.

## 3. Start

```bash
docker compose -f docker-compose.yml -f docker/docker-compose.prod.yml up -d --build
docker compose ps           # all services "Up" / "healthy"
docker compose logs -f api  # watch the start-up
```

The production override hides the API port and binds the dashboard to `127.0.0.1:8080` so that only the HTTPS proxy can reach it.

## 4. HTTPS with Caddy (automatic certificates)

```bash
sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
social.yourcompany.com {
    reverse_proxy 127.0.0.1:8080
}
EOF
sudo systemctl reload caddy
```

Open `https://social.yourcompany.com` and log in.

## 5. Backups

```bash
# daily database dump (add to crontab)
docker compose exec -T db pg_dump -U insta insta | gzip > /backups/insta-$(date +%F).sql.gz
# media files (generated images), unless you use S3
docker run --rm -v instagram-automation_media:/m -v /backups:/b alpine tar czf /b/media-$(date +%F).tgz -C /m .
```

## 6. Updating

```bash
git pull
docker compose -f docker-compose.yml -f docker/docker-compose.prod.yml up -d --build
```

Database migrations run automatically when the `api` container starts (`alembic upgrade head`).

## Scaling later

- Move PostgreSQL to a managed database (set `DATABASE_URL`), Redis to a managed Redis (`REDIS_URL`), and images to S3/R2 (`STORAGE_BACKEND=s3`).
- Run several `api` and `worker` containers. Duplicate-publish protection is in the database, so this is safe.
- Always run **exactly one** `beat` container.
- The frontend is static files; it can also be hosted on any CDN, with `/api` routed to the backend.
