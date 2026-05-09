# Ohabai Pipeline

Connector-agnostic omnichannel inbox CRM. Flask + PostgreSQL + SQLAlchemy.
13 tables. No browser automation, no whatsapp-web.js, no local bridge.

## Repo layout

    ohabai-pipeline/
      app.py                        # Flask API
      models.py                     # SQLAlchemy models (13 tables)
      seed.py                       # creates test company + channel_account
      smoke.sh                      # local end-to-end smoke test
      requirements.txt
      Procfile                      # Railway: gunicorn -w 2 -b 0.0.0.0:$PORT app:app
      runtime.txt                   # Railway pins python-3.11.9
      .env.example
      connectors/
        whatsapp-baileys/           # Phase 2 - one process per WhatsApp account

## Local setup

End-to-end local test: backend on localhost:5001 -> Postgres on
localhost:5432 -> Baileys connector talking to both.

### 1. Install Postgres (one time)

    brew install postgresql@16
    brew services start postgresql@16

### 2. Create the database

    createdb ohabai_pipeline

### 3. Configure backend env

    cd ~/Desktop/ohabai-pipeline
    cp .env.example .env

Defaults match Homebrew Postgres on Mac. Use PORT=5001 to avoid macOS
AirPlay Receiver on port 5000.

### 4. Install Python deps

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

If psycopg2-binary fails to build, your Python is too new. Use 3.12:

    brew install python@3.12
    /opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv

### 5. Seed the DB

    python3 seed.py

Creates all tables, inserts one Company and one ChannelAccount,
prints UUIDs. Idempotent.

### 6. Start the backend

    python3 app.py

Verify: curl -s http://localhost:5001/api/health

### 7. Configure connector env

    cd connectors/whatsapp-baileys
    cp .env.example .env

Paste the UUIDs from step 5 into .env.

### 8. Smoke test (optional)

    set -a; source connectors/whatsapp-baileys/.env; set +a
    ./smoke.sh

### 9. Start the connector and scan QR

    cd connectors/whatsapp-baileys
    npm start

Scan QR -> WhatsApp -> Settings -> Linked Devices -> Link a device.

## Production deployment (Railway)

GitHub-driven workflow: push to master -> Railway auto-deploys.

### One-time setup

1. Push the repo to GitHub.
2. railway.app -> New Project -> Deploy from GitHub repo.
3. Add Postgres: project view -> + Create -> Database -> PostgreSQL.
4. On the web service, Variables tab, add:
   - DATABASE_URL = ${{Postgres.DATABASE_URL}}  (use the Reference picker, not a literal value)
   - SECRET_KEY = any non-empty string
5. web service -> Settings -> Networking -> Generate Domain.

### Bootstrap the production DB

Tables auto-create on startup via db.create_all(). To insert the first
company + channel_account, run seed.py against the **public** Postgres
URL (the internal postgres.railway.internal hostname only resolves
between services inside Railway):

1. Postgres service -> Variables -> reveal DATABASE_PUBLIC_URL.
   Looks like postgresql://postgres:<pw>@viaduct.proxy.rlwy.net:<port>/railway
2. From your laptop:

       cd ~/Desktop/ohabai-pipeline
       source .venv/bin/activate
       DATABASE_URL="<paste-public-url>" python3 seed.py

3. Note the printed COMPANY_ID and CHANNEL_ACCOUNT_ID. Production has
   its own DB - these are different from the local ones.

### Verify against production

    PIPELINE_API_URL=https://<your-railway-domain> \
    COMPANY_ID=<production-company-id> \
    CHANNEL_ACCOUNT_ID=<production-channel-account-id> \
    ./smoke.sh

All five steps should pass.

### Point the connector at production

Edit connectors/whatsapp-baileys/.env with production values, then
restart the connector. Because auth dirs are keyed by
CHANNEL_ACCOUNT_ID, switching to a new id triggers a fresh QR.

If the startup banner still shows old values after editing .env,
it's because Node's dotenv does not override existing process.env.
Unset stale shell exports first:

    unset PIPELINE_API_URL COMPANY_ID CHANNEL_ACCOUNT_ID
    npm start

### Updating

Push to master -> Railway auto-redeploys. Force a redeploy via the
dashboard (Deployments -> Deploy latest) or `railway up` from CLI.

## Connector contract

Each connector binds to one channel_account_id and:

1. POSTs heartbeat to /api/connectors/heartbeat every ~15s
2. POSTs inbound to /api/connectors/inbound (idempotent on external_message_id)
3. Polls /api/outbound-queue/poll, sends, PATCHes /api/outbound-queue/<id>

The schema does not change to add a new channel.

## API reference

- GET   /api/conversations (header X-Company-ID)
- GET   /api/conversations/<id>/messages
- POST  /api/conversations/<id>/send - enqueue outbound
- POST  /api/contacts / PATCH /api/contacts/<id>
- POST  /api/channel-accounts
- POST  /api/connectors/heartbeat
- POST  /api/connectors/inbound
- POST  /api/outbound-queue/poll
- PATCH /api/outbound-queue/<id>
- GET   /api/health

## Troubleshooting

Backend hangs on startup -> Postgres not running. brew services start postgresql@16.

Seed fails with connection refused (local) -> DATABASE_URL wrong or Postgres not started.

Seed fails with "could not translate host name postgres.railway.internal" -> you tried to use the internal Railway URL from your laptop. Use DATABASE_PUBLIC_URL instead (Postgres service -> Variables tab).

Connector heartbeat failed ECONNREFUSED -> backend not running, or wrong PIPELINE_API_URL.

Connector inbound POST failed 404 -> CHANNEL_ACCOUNT_ID does not match a row in the target backend. Re-run seed.py against that backend.

Connector startup banner shows wrong values -> stale shell exports shadowing dotenv. unset PIPELINE_API_URL COMPANY_ID CHANNEL_ACCOUNT_ID before npm start.

macOS port 5000 returns 403 -> AirPlay Receiver. Use port 5001 for local Flask.
