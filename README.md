# Ohabai Pipeline - Phase 1
Connector-agnostic omnichannel inbox CRM. Flask + PostgreSQL + SQLAlchemy.
13 tables. No browser automation, no whatsapp-web.js, no local bridge.

## Connector contract (Phase 2+)
Each connector binds to one channel_account_id and:
1. POSTs heartbeat to /api/connectors/heartbeat
2. POSTs inbound to /api/connectors/inbound (dedup on external_message_id)
3. Polls /api/outbound-queue/poll, sends, PATCHes /api/outbound-queue/<id>

## Run
cp .env.example .env  # edit DATABASE_URL
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
