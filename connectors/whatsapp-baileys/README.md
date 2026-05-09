# Ohabai WhatsApp Baileys Connector

Headless Node.js process that bridges one WhatsApp account to the
Ohabai Pipeline backend. One process per WhatsApp account.

## What it does

- QR-links to WhatsApp Web via Baileys; multi-file auth persisted to disk
- Inbound: every WA message -> POST /api/connectors/inbound (idempotent on external_message_id)
- Outbound: poll /api/outbound-queue/poll every POLL_INTERVAL_MS, send via Baileys, PATCH back
- Heartbeat every HEARTBEAT_INTERVAL_MS; sends X-Connector-Secret on every request
- Reconnect: exponential backoff 2s -> 60s on connection drops
- Health endpoint: HTTP /health on HEALTH_PORT (default 3000)

## Local development

### 1. Install

    npm install

Requires Node.js 20+.

### 2. Configure

    cp .env.example .env

Edit `.env` with local backend URL and seed UUIDs. Leave
HEALTH_PORT=3100 for local dev so the connector's health endpoint
doesn't collide with the frontend dev server on port 3000.

### 3. Run

    npm start

Scan QR in WhatsApp -> Settings -> Linked Devices -> Link a device.

## Production deployment (VPS)

Always-on Linux VPS via Docker Compose. Tested on Ubuntu 24.04 LTS.
1 vCPU and 1 GB RAM is enough for one WhatsApp account.

Reasonable providers: Hetzner CX11, DigitalOcean Basic Droplet,
Vultr Cloud Compute. Any Ubuntu 22.04+ box with Docker support works.

### Final deployment checklist

Each step is a yes/no check. Follow in order.

#### Prerequisites

- VPS provisioned (1 vCPU, 1 GB RAM, Ubuntu 24.04 LTS)
- SSH access as root
- Production CONNECTOR_SECRET in hand (must match Railway env var)
- Production COMPANY_ID and CHANNEL_ACCOUNT_ID in hand

#### 1. Bootstrap the host

SSH in as root, then:

    git clone https://github.com/taxiproduction2002-sys/ohabai-pipeline.git /opt/ohabai-pipeline
    sudo bash /opt/ohabai-pipeline/connectors/whatsapp-baileys/scripts/vps-setup.sh

Verify:

    docker --version
    docker compose version
    id ohabai

#### 2. Switch to the ohabai user

    su - ohabai
    git clone https://github.com/taxiproduction2002-sys/ohabai-pipeline.git
    cd ohabai-pipeline/connectors/whatsapp-baileys

#### 3. Configure .env.production

    cp .env.production.example .env.production
    nano .env.production

Required values:

    NODE_ENV=production
    PIPELINE_API_URL=https://web-production-bc34a.up.railway.app
    COMPANY_ID=<your production COMPANY_ID>
    CHANNEL_ACCOUNT_ID=<your production CHANNEL_ACCOUNT_ID>
    CONNECTOR_SECRET=<must match Railway env exactly>
    POLL_INTERVAL_MS=3000
    HEARTBEAT_INTERVAL_MS=15000
    HEALTH_PORT=3000

#### 4. Bring up the container

    docker compose up -d
    docker compose ps
    docker compose logs --tail 50

First time builds the image (~1-2 min).

#### 5. Stop the laptop connector

If the connector is still running on your laptop, Ctrl+C in that tab
now. Only one device should hold the WA session.

#### 6. Scan QR

    docker compose logs -f

Wait for the QR. Scan from your phone: WhatsApp -> Settings ->
Linked Devices -> Link a device. After "connection open", Ctrl+C
to detach (container keeps running).

#### 7. Local health check

    curl http://localhost:3000/health

Should return 200 with `"status":"ok"`.

#### 8. Verify backend is receiving heartbeats

From your laptop:

    curl -s -H "X-Company-ID: <YOUR-COMPANY-ID>" \
      https://web-production-bc34a.up.railway.app/api/connector-status \
      | python3 -m json.tool

`seconds_since_heartbeat` should be small. `effective_status: "online"`.

#### 9. End-to-end test

- Open the inbox, badge should be green
- Send a WhatsApp message to your bridged number from another phone
- Inbox should show it within ~3 seconds
- Reply via the composer; phone receives within ~3 seconds
- Close your laptop for 30 seconds
- Send another inbound message
- Reopen laptop, frontend should show the new message
- Confirmed working without the laptop holding the connector

### Migrating from a local connector

The auth folder is not migrated automatically. Two options:

**Clean re-link** (recommended): Stop the laptop connector. Deploy
to VPS. Scan the new QR - WhatsApp transparently re-links to the new
device, the laptop instance is disconnected.

**Preserve session**: Stop the laptop connector. scp
`auth/<channel_id>/` to
`<vps>:/home/ohabai/ohabai-pipeline/connectors/whatsapp-baileys/data/auth/<channel_id>/`.
Then `docker compose up -d` on the VPS. No QR needed. Only one device
can hold the session - copy once, then never run the laptop instance.

## Operational runbook (VPS)

All commands assume you're SSH'd in as the `ohabai` user, in
`~/ohabai-pipeline/connectors/whatsapp-baileys/`.

### Restart the connector

    docker compose restart

### Check logs

    docker compose logs -f                # tail live
    docker compose logs --since 1h
    docker compose logs --tail 100
    docker compose logs | jq 'select(.level == "error")'

### Health check

    curl http://localhost:3000/health

### Verify auth and cache volumes

    ls -la data/auth/<channel_account_id>/
    ls -la data/cache/<channel_account_id>/

`auth/` should contain `creds.json` and many `session-*.json` files
once a QR has been scanned. `cache/` should contain `thread-cache.json`
once messages have flowed. If either is empty after the connector has
been running, the bind mount may be misconfigured - check
`docker compose config` and ensure the `volumes:` block matches.

### Re-scan QR

    docker compose down
    rm -rf data/auth/<channel_account_id>/
    docker compose up -d
    docker compose logs -f

### Rotate the connector secret

1. Generate:

       python3 -c "import secrets; print(secrets.token_urlsafe(48))"

2. Railway dashboard -> web service -> Variables -> edit
   CONNECTOR_SECRET. Connector will 401-storm for ~1-2 min during
   redeploy.

3. On VPS:

       sed -i "s|^CONNECTOR_SECRET=.*|CONNECTOR_SECRET=<new>|" .env.production
       docker compose down
       docker compose up -d

### Update connector code

    cd ~/ohabai-pipeline
    git pull
    cd connectors/whatsapp-baileys
    docker compose build
    docker compose up -d

Auth and cache survive the rebuild; no QR re-scan needed.

### Stop / nuke

    docker compose stop                   # pause, keep volumes
    docker compose start                  # resume
    docker compose down                   # remove container, keep volumes
    docker compose down -v                # remove + DELETE volumes (loses auth)

## Environment variables

| Variable               | Required   | Default | Notes                                |
|------------------------|------------|---------|--------------------------------------|
| PIPELINE_API_URL       | yes        | -       | Backend base URL                     |
| COMPANY_ID             | yes        | -       | Tenant UUID                          |
| CHANNEL_ACCOUNT_ID     | yes        | -       | Channel UUID; keys auth dir          |
| CONNECTOR_SECRET       | yes (prod) | -       | X-Connector-Secret; must match backend |
| POLL_INTERVAL_MS       | no         | 3000    | Outbound queue poll interval         |
| HEARTBEAT_INTERVAL_MS  | no         | 15000   | Heartbeat send interval              |
| HEALTH_PORT            | no         | 3000    | /health port (use 3100 locally)      |
| LOG_LEVEL              | no         | info    | pino level                           |
| NODE_ENV               | no         | -       | "production" enables JSON logs       |
