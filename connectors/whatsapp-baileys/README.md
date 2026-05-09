# Ohabai Pipeline - WhatsApp (Baileys) connector

Headless Node.js connector that bridges one WhatsApp account into the
Ohabai Pipeline backend. No browser, no Chromium, no whatsapp-web.js,
no Mac UI. One process per WhatsApp account.

## What this does

- QR-login to WhatsApp Web. Multi-file auth persisted under
  `./auth/<channel_account_id>/` so restarts skip the QR.
- Streams inbound messages to `POST /api/connectors/inbound`. The backend
  dedups on `external_message_id`, so re-delivery is safe.
- Heartbeats every 15s to `POST /api/connectors/heartbeat` with status
  `online | offline | reconnecting` and `last_error` (if any).
- Polls `POST /api/outbound-queue/poll` every 3s (configurable), sends
  each claimed item via Baileys, then PATCHes the queue item to
  `sent` (with `external_message_id`) or `failed` (with `error_message`).
- Caches `conversation_id -> chat JID` to
  `./cache/<channel_account_id>/thread-cache.json` so outbound knows
  where to send.

## Phase 2 scope

Text in, text out. Inbound captures metadata for image / video / audio /
voice / file / sticker (mime, size, dimensions, duration), but media
files are NOT downloaded yet. Outbound is text-only.

## 1. Create the channel_account row

Before running, create the row in the Pipeline backend so you have a
`channel_account_id`:

    curl -X POST http://localhost:5000/api/channel-accounts \
      -H 'Content-Type: application/json' \
      -H "X-Company-ID: $COMPANY_ID" \
      -d '{
        "channel_type": "whatsapp",
        "connector_type": "whatsapp_baileys",
        "display_name": "My WhatsApp",
        "status": "pending"
      }'

The response gives you an `id` - that's your `CHANNEL_ACCOUNT_ID`.

## 2. Configure

    cd connectors/whatsapp-baileys
    cp .env.example .env
    # edit .env with PIPELINE_API_URL, COMPANY_ID, CHANNEL_ACCOUNT_ID
    npm install

## 3. Run

    npm start

On first run a QR appears in the terminal. Open WhatsApp on your phone:
Settings -> Linked Devices -> Link a device -> scan. Auth is saved
under `./auth/<channel_account_id>/` so subsequent restarts skip QR.

## QR / login flow

- First run: no `./auth/<channel_account_id>/creds.json` -> Baileys
  emits `qr` on `connection.update` -> printed in terminal.
- After scan: connection state goes to `open`, status flips to `online`,
  next heartbeat reflects this.
- Logged out from phone: connector deletes `./auth/<channel_account_id>/`,
  exits with code 1, requires manual restart and a new scan.

## Known limitations

- One WhatsApp account per process. Multi-account is Phase 3.
- No media upload or download yet. Inbound captures metadata only.
- No typing indicators, read receipts, or presence are relayed.
- Outbound thread JID resolution depends on either (a) the conversation
  having seen at least one inbound message (cache hit) or (b) being
  present in the first 200 conversations returned by
  `GET /api/conversations` (fallback). Cold proactive outbound to a
  brand-new number isn't supported until Phase 3.
- Group chats: inbound works (sender = participant JID, thread = group
  JID `<id>@g.us`). Outbound to groups works the same way as 1:1.
- `status@broadcast` is ignored.
- `fromMe` messages are skipped to avoid duplicating outbound that the
  Pipeline queue already tracks.

## Logs

- `info`: connection state, inbound, outbound, heartbeat lifecycle.
- `warn`: poll failures, heartbeat failures, recoverable disconnects.
- `error`: send failures, message handler errors.
- Message text is truncated to 30-char previews. Full content is never
  logged.

## Files this creates

- `./auth/<channel_account_id>/` - Baileys session (gitignored, sensitive)
- `./cache/<channel_account_id>/thread-cache.json` - conv -> JID map
