# Ohabai WhatsApp Baileys Connector

Headless Node.js process that bridges one WhatsApp account to the
Ohabai Pipeline backend. One process per WhatsApp account.

## What it does

- QR-links to WhatsApp Web via Baileys; multi-file auth persisted to disk
- Inbound: every WA message -> POST /api/connectors/inbound (idempotent on external_message_id)
- Outbound: poll /api/outbound-queue/poll every 3s, send via Baileys, PATCH back
- Heartbeat every 15s
- Reconnect: exponential backoff 2s -> 60s on connection drops
- Health endpoint: HTTP /health on HEALTH_PORT (default 3000)

## Local development

### 1. Install

    npm install

Requires Node.js 20+.

### 2. Configure

    cp .env.example .env

Edit .env with local backend URL and the seed UUIDs:

    PIPELINE_API_URL=http://localhost:5001
    COMPANY_ID=<from local seed.py>
    CHANNEL_ACCOUNT_ID=<from local seed.py>

### 3. Run

    npm start

Scan QR in WhatsApp -> Settings -> Linked Devices -> Link a device.

## Production deployment (VPS)

Always-on Linux VPS via Docker Compose. Tested on Ubuntu 24.04 LTS.
1 vCPU and 1 GB RAM is enough for one WhatsApp account.

Reasonable providers: Hetzner CX11, DigitalOcean Basic Droplet,
Vultr Cloud Compute. Any Ubuntu 22.04+ box with Docker support works.

### 1. Provision the VPS

Spin up Ubuntu 24.04 LTS. SSH in as root.

### 2. Bootstrap

After cloning the repo on the VPS:

    sudo bash connectors/whatsapp-baileys/scripts/vps-setup.sh

Installs Docker + Compose plugin, enables Docker on boot, creates an
`ohabai` user in the docker group.

### 3. Clone and configure

    su - ohabai
    git clone https://github.com/taxiproduction2002-sys/ohabai-pipeline.git
    cd ohabai-pipeline/connectors/whatsapp-baileys
    cp .env.production.example .env.production

Edit .env.production with production UUIDs and a connector secret:

    PIPELINE_API_URL=https://web-production-bc34a.up.railway.app
    COMPANY_ID=9b6665fc-8c3a-451a-8bd5-c559ce9ceb00
    CHANNEL_ACCOUNT_ID=657c2819-9b75-4da0-8d27-647757e02c65
    CONNECTOR_SECRET=<any non-empty string>

### 4. Start

    docker compose up -d
    docker compose logs -f

On first run you'll see a QR. Scan from your phone - this re-links
the WA account to the VPS, replacing whichever device was linked
before. After "connection open", Ctrl+C to detach (container keeps
running).

### 5. Verify

    curl -s http://<vps-ip>:3000/health

Returns 200 with status "ok" when online; 503 degraded otherwise.

### 6. Auto-recovery

- Container exits -> Docker restarts (restart: unless-stopped).
- Host reboots -> Docker daemon up -> container up.
- WA connection drops -> exponential backoff reconnect (2s, 4s, ..., 60s max).

### Migrating from a local connector

The auth folder is not migrated automatically. Two options:

**Clean re-link** (recommended): Stop the laptop connector. Deploy
to VPS. Scan the new QR - WhatsApp transparently re-links to the new
device, the laptop instance is disconnected.

**Preserve session**: Stop the laptop connector. scp
`auth/<channel_id>/` to
`<vps>:/home/ohabai/ohabai-pipeline/connectors/whatsapp-baileys/data/auth/<channel_id>/`.
Then `docker compose up -d` on the VPS. Only one device can hold the
session at a time - copy once, then never run the laptop instance
again or both will fight.

## Operational runbook (VPS)

All commands below assume you're SSH'd in as the `ohabai` user, in
`~/ohabai-pipeline/connectors/whatsapp-baileys/`.

### Restart the connector

    docker compose restart

Container goes down, comes back, reconnects to WhatsApp using saved
auth, resumes heartbeats and queue polling. No QR re-scan needed.

### Check logs

    docker compose logs -f                # tail live
    docker compose logs --since 1h        # last hour
    docker compose logs --tail 100        # last 100 lines
    docker compose logs | jq 'select(.level == "error")'   # errors only

JSON-formatted in production. Pretty-printed in dev.

### Health check

    curl http://localhost:3000/health

200 ok = online. 503 degraded = reconnecting or offline. Run from
the VPS host, or from outside via the VPS public IP and port 3000.

### Re-scan QR (re-link WhatsApp)

When to do this:
- WA session was unlinked (someone scanned a new QR for the same
  number, or you logged the device out from your phone)
- Auth directory got corrupted
- Connector logs say "logged out - clearing auth, restart required"
- Moving the connector to a new server

How:

    docker compose down
    rm -rf data/auth/<channel_account_id>/
    docker compose up -d
    docker compose logs -f

Watch logs until QR appears. Scan from phone: WhatsApp -> Settings ->
Linked Devices -> Link a device. After "connection open" appears,
Ctrl+C to detach (container keeps running).

### Rotate the connector secret

1. Generate a new value:

       python3 -c "import secrets; print(secrets.token_urlsafe(48))"

2. Update Railway: web service -> Variables -> edit CONNECTOR_SECRET
   with new value. Railway redeploys ~1-2 min. During this window
   the connector will 401-storm; expected.

3. On the VPS, update .env.production and restart:

       sed -i "s|^CONNECTOR_SECRET=.*|CONNECTOR_SECRET=<new value>|" .env.production
       docker compose down
       docker compose up -d

Both sides match again, 401s stop within the next heartbeat tick.

### Update connector code

After pushing new code to GitHub master:

    cd ~/ohabai-pipeline
    git pull
    cd connectors/whatsapp-baileys
    docker compose build
    docker compose up -d

Auth and cache volumes survive the rebuild; no QR re-scan needed.

### Stop / nuke

    docker compose stop                   # pause, keep volumes
    docker compose start                  # resume
    docker compose down                   # remove container, keep volumes
    docker compose down -v                # remove + DELETE volumes (loses auth)

Use `down -v` only if you intend to re-scan QR from scratch.

## Environment variables

| Variable           | Required | Default | Notes                              |
|--------------------|----------|---------|------------------------------------|
| PIPELINE_API_URL   | yes      | -       | Backend base URL                   |
| COMPANY_ID         | yes      | -       | Tenant UUID                        |
| CHANNEL_ACCOUNT_ID | yes      | -       | Channel UUID; keys auth dir        |
| CONNECTOR_SECRET   | no       | -       | Sent as X-Connector-Secret         |
| POLL_INTERVAL_MS   | no       | 3000    | Outbound queue poll interval       |
| LOG_LEVEL          | no       | info    | pino level                         |
| HEALTH_PORT        | no       | 3000    | HTTP /health                       |
| NODE_ENV           | no       | -       | "production" enables JSON logs     |
