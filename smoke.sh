#!/bin/bash
# Local smoke test for Ohabai Pipeline + Baileys connector.
# Verifies: backend health, inbound ingest, conversation creation,
# outbound enqueue, queue poll. Stop the connector before running this
# (otherwise it may claim the queue item before step 5).

set -e

API="${PIPELINE_API_URL:-http://localhost:5000}"

if [ -z "$COMPANY_ID" ] || [ -z "$CHANNEL_ACCOUNT_ID" ]; then
  echo "ERROR: set COMPANY_ID and CHANNEL_ACCOUNT_ID env vars first."
  echo "Hint: set -a; source connectors/whatsapp-baileys/.env; set +a"
  exit 1
fi

pp() { python3 -m json.tool; }

echo "--- Smoke test against $API ---"

echo
echo "[1/5] GET /api/health"
curl -fsS "$API/api/health" | pp

echo
echo "[2/5] GET /api/conversations"
curl -fsS -H "X-Company-ID: $COMPANY_ID" "$API/api/conversations" | pp

EMID="smoke-$(date +%s)-$$"
TJID="60123456789@s.whatsapp.net"
echo
echo "[3/5] POST /api/connectors/inbound (simulated WA inbound, emid=$EMID)"
INBOUND_RES=$(curl -fsS -X POST "$API/api/connectors/inbound" \
  -H 'Content-Type: application/json' \
  -d "{
    \"channel_account_id\": \"$CHANNEL_ACCOUNT_ID\",
    \"external_message_id\": \"$EMID\",
    \"external_thread_id\": \"$TJID\",
    \"sender_external_id\": \"60123456789\",
    \"sender_name\": \"Smoke Tester\",
    \"text\": \"Smoke test inbound message\",
    \"message_type\": \"text\",
    \"platform_timestamp\": $(date +%s)
  }")
echo "$INBOUND_RES" | pp

CONV_ID=$(echo "$INBOUND_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['conversation_id'])")
echo "  -> conversation_id=$CONV_ID"

echo
echo "[4/5] POST /api/conversations/$CONV_ID/send (enqueue outbound)"
SEND_RES=$(curl -fsS -X POST "$API/api/conversations/$CONV_ID/send" \
  -H 'Content-Type: application/json' \
  -H "X-Company-ID: $COMPANY_ID" \
  -d '{"text": "Smoke test outbound reply"}')
echo "$SEND_RES" | pp

echo
echo "[5/5] POST /api/outbound-queue/poll (claim items as connector)"
POLL_RES=$(curl -fsS -X POST "$API/api/outbound-queue/poll" \
  -H 'Content-Type: application/json' \
  -d "{
    \"channel_account_id\": \"$CHANNEL_ACCOUNT_ID\",
    \"connector_id\": \"smoke-test\",
    \"limit\": 5
  }")
echo "$POLL_RES" | pp

CLAIMED=$(echo "$POLL_RES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['items']))")
echo
if [ "$CLAIMED" -gt 0 ]; then
  echo "PASS - $CLAIMED queue item(s) claimed."
else
  echo "WARN - no items claimed. If a real connector is running, it may have grabbed them first."
fi
