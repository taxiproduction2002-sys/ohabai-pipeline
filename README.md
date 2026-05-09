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
      .env.example
      connectors/
        whatsapp-baileys/           # Phase 2 - one process per WhatsApp account

## Local setup

End-to-end local test: backend on `localhost:5000` -> Postgres on
`localhost:5432` -> Baileys connector talking to both.

### 1. Install Postgres (one time)

    brew install postgresql@16
    brew services start postgresql@16

This runs Postgres as your macOS user with no password.

### 2. Create the database

    createdb ohabai_pipeline

### 3. Configure backend env

    cd ~/Desktop/ohabai-pipeline
    cp .env.example .env

The defaults match Homebrew Postgres on Mac. No edits needed unless your
setup differs.

### 4. Install Python deps

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

### 5. Seed the DB

    python3 seed.py

This creates all tables, inserts one Company and one ChannelAccount,
and prints two UUIDs. Idempotent.

### 6. Start the backend

In one terminal tab, with the venv active:

    python3 app.py

Verify in another tab:

    curl -s http://localhost:5000/api/health

Should return JSON with status ok.

### 7. Configure connector env

    cd ~/Desktop/ohabai-pipeline/connectors/whatsapp-baileys
    cp .env.example .env

Open .env and paste in the two UUIDs from step 5.

### 8. Run the smoke test

Back in the pipeline root, with the backend still running:

    set -a; source connectors/whatsapp-baileys/.env; set +a
    ./smoke.sh

All five steps should print JSON with no errors.

### 9. Start the connector and scan QR

    cd connectors/whatsapp-baileys
    npm start

Scan the QR with WhatsApp -> Settings -> Linked Devices.

## Connector contract

Each connector binds to one channel_account_id and:

1. POSTs heartbeat to /api/connectors/heartbeat every ~15s
2. POSTs inbound to /api/connectors/inbound (idempotent on external_message_id)
3. Polls /api/outbound-queue/poll, sends, PATCHes /api/outbound-queue/<id>

The schema does not change to add a new channel.

## API reference

- GET  /api/conversations (header X-Company-ID)
- GET  /api/conversations/<id>/messages
- POST /api/conversations/<id>/send - enqueue outbound
- POST /api/contacts / PATCH /api/contacts/<id>
- POST /api/channel-accounts
- POST /api/connectors/heartbeat
- POST /api/connectors/inbound
- POST /api/outbound-queue/poll
- PATCH /api/outbound-queue/<id>
- GET  /api/health

## Troubleshooting

Backend hangs on startup -> Postgres not running. Run brew services start postgresql@16.

Seed fails with connection refused -> DATABASE_URL wrong, or Postgres not started.

Connector logs heartbeat failed ECONNREFUSED -> backend not running.

Connector logs inbound POST failed 404 -> CHANNEL_ACCOUNT_ID does not match seeded row. Re-run seed.py and copy UUID again.
