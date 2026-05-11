"""Ohabai Pipeline backend. Connector-agnostic; connectors plug in via /api/connectors/* and /api/outbound-queue/*."""
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from sqlalchemy import desc, text
from models import (db, Company, User, ChannelAccount, Contact, Conversation,
                    ConversationParticipant, Message, MessageAttachment,
                    MessageDeliveryStatus, AIMemoryBlock, AIReplySuggestion,
                    OutboundMessageQueue, ConnectorHeartbeat)

app = Flask(__name__)
CORS(app, resources={r'/api/*': {'origins': '*'}})

db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/ohabai_pipeline")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
db.init_app(app)


def run_migrations():
    """Idempotent column additions for legacy tables. Postgres-only."""
    with db.engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE channel_accounts "
            "ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE channel_accounts "
            "ADD COLUMN IF NOT EXISTS last_error TEXT"
        ))


with app.app_context():
    db.create_all()
    try:
        run_migrations()
    except Exception as e:
        app.logger.warning("run_migrations skipped: %s", e)


# ---------- helpers ----------
def get_company_id(): return request.headers.get("X-Company-ID")
def serialize_dt(dt): return dt.isoformat() if dt else None
def err(msg, status=400): return jsonify({"error": msg}), status


# ---------- connector secret enforcement ----------
# Fail-open if CONNECTOR_SECRET env is not set on the backend (dev mode).
# Fail-closed (401) once env var is present.
def require_connector_secret(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        expected = os.environ.get("CONNECTOR_SECRET")
        if expected:
            sent = request.headers.get("X-Connector-Secret")
            if not sent or sent != expected:
                app.logger.warning(
                    "rejected connector request: missing/invalid X-Connector-Secret on %s",
                    request.path,
                )
                return jsonify({"error": "invalid connector secret"}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------- queue cleanup ----------
STUCK_PROCESSING_MINUTES = 5

def cleanup_stuck_queue_items():
    """Items locked >5min are reset to queued (or failed if at max attempts)."""
    cutoff = datetime.utcnow() - timedelta(minutes=STUCK_PROCESSING_MINUTES)
    stuck = OutboundMessageQueue.query.filter(
        OutboundMessageQueue.status == "processing",
        OutboundMessageQueue.locked_at < cutoff,
    ).all()
    reset, failed = 0, 0
    for it in stuck:
        if (it.attempts or 0) >= (it.max_attempts or 3):
            it.status = "failed"
            it.error_message = (it.error_message or "") + " [stuck-cleanup-timeout]"
            failed += 1
        else:
            it.status = "queued"
            it.locked_at = None
            it.locked_by = None
            reset += 1
        app.logger.warning(
            "stuck queue item %s (attempts=%s) -> %s",
            it.id, it.attempts, it.status,
        )
    if stuck:
        db.session.commit()
    return {"reset": reset, "failed": failed, "scanned": len(stuck)}


# ---------- conversation routes ----------
@app.route("/api/conversations", methods=["GET"])
def list_conversations():
    cid = get_company_id()
    if not cid:
        return err("X-Company-ID header required")
    status = request.args.get("status", "open")
    chid = request.args.get("channel_account_id")
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50
    q = Conversation.query.filter_by(company_id=cid)
    if status and status != "all":
        q = q.filter_by(status=status)
    if chid:
        q = q.filter_by(channel_account_id=chid)
    convs = q.order_by(desc(Conversation.last_message_at)).limit(limit).all()
    out = []
    for c in convs:
        ct = db.session.get(Contact, c.contact_id) if c.contact_id else None
        out.append({"id": c.id, "channel_account_id": c.channel_account_id,
                    "contact_id": c.contact_id, "contact_name": ct.display_name if ct else None,
                    "external_thread_id": c.external_thread_id, "status": c.status,
                    "assigned_user_id": c.assigned_user_id,
                    "last_message_at": serialize_dt(c.last_message_at),
                    "last_message_preview": c.last_message_preview,
                    "unread_count": c.unread_count or 0})
    return jsonify({"conversations": out})


@app.route("/api/conversations/<conv_id>/messages", methods=["GET"])
def get_messages(conv_id):
    cid = get_company_id()
    conv = Conversation.query.filter_by(id=conv_id, company_id=cid).first()
    if not conv:
        return err("conversation not found", 404)
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50
    before_id = request.args.get("before_id")
    q = Message.query.filter_by(conversation_id=conv_id)
    if before_id:
        bm = db.session.get(Message, before_id)
        if bm:
            q = q.filter(Message.created_at < bm.created_at)
    msgs = q.order_by(desc(Message.created_at)).limit(limit).all()
    msgs.reverse()
    # Phase 9A: pre-fetch Contact display_names for group chat attribution
    _sender_ids = {m.sender_contact_id for m in msgs if m.sender_contact_id}
    _sender_names = {}
    if _sender_ids:
        for _c in Contact.query.filter(Contact.id.in_(_sender_ids)).all():
            _sender_names[_c.id] = _c.display_name or ""
    out = []
    for m in msgs:
        atts = MessageAttachment.query.filter_by(message_id=m.id).all()
        out.append({"id": m.id, "direction": m.direction, "message_type": m.message_type,
                    "text_content": m.text_content, "sender_type": m.sender_type,
                    "sender_contact_id": m.sender_contact_id, "sender_user_id": m.sender_user_id,
                    "sender_external_id": m.sender_external_id,
                    "sender_name": _sender_names.get(m.sender_contact_id),
                    "external_message_id": m.external_message_id,
                    "quoted_message_id": m.quoted_message_id,
                    "platform_timestamp": serialize_dt(m.platform_timestamp),
                    "created_at": serialize_dt(m.created_at),
                    "attachments": [{"id": a.id, "attachment_type": a.attachment_type,
                                     "file_url": a.file_url, "file_name": a.file_name,
                                     "file_size": a.file_size, "mime_type": a.mime_type,
                                     "duration_seconds": a.duration_seconds,
                                     "width": a.width, "height": a.height,
                                     "thumbnail_url": a.thumbnail_url} for a in atts]})
    return jsonify({"messages": out})


@app.route("/api/conversations/<conv_id>/send", methods=["POST"])
def send_message(conv_id):
    cid = get_company_id()
    conv = Conversation.query.filter_by(id=conv_id, company_id=cid).first()
    if not conv:
        return err("conversation not found", 404)
    b = request.get_json(silent=True) or {}
    text_in = b.get("text")
    atts = b.get("attachments") or []
    if not text_in and not atts:
        return err("text or attachments required")
    item = OutboundMessageQueue(
        conversation_id=conv.id, channel_account_id=conv.channel_account_id,
        payload={"text": text_in, "attachments": atts,
                 "quoted_external_id": b.get("quoted_external_id"),
                 "message_type": b.get("message_type", "text")},
        status="queued", created_by_user_id=b.get("user_id"))
    db.session.add(item); db.session.commit()
    return jsonify({"queue_id": item.id, "status": item.status,
                    "created_at": serialize_dt(item.created_at)}), 202


# ---------- contacts ----------
@app.route("/api/contacts", methods=["POST"])
def create_contact():
    cid = get_company_id()
    if not cid:
        return err("X-Company-ID required")
    b = request.get_json(silent=True) or {}
    c = Contact(company_id=cid, display_name=b.get("display_name"),
                primary_phone=b.get("primary_phone"), primary_email=b.get("primary_email"),
                profile_picture_url=b.get("profile_picture_url"), notes=b.get("notes"),
                external_handles=b.get("external_handles") or {},
                tags=b.get("tags") or [])
    db.session.add(c); db.session.commit()
    return jsonify({"id": c.id}), 201


@app.route("/api/contacts/<contact_id>", methods=["PATCH"])
def update_contact(contact_id):
    cid = get_company_id()
    c = Contact.query.filter_by(id=contact_id, company_id=cid).first()
    if not c:
        return err("not found", 404)
    b = request.get_json(silent=True) or {}
    for f in ("display_name", "primary_phone", "primary_email",
              "profile_picture_url", "notes", "external_handles", "tags"):
        if f in b:
            setattr(c, f, b[f])
    db.session.commit()
    return jsonify({"id": c.id})


# ---------- channel accounts ----------
@app.route("/api/channel-accounts", methods=["POST"])
def create_channel_account():
    cid = get_company_id()
    if not cid:
        return err("X-Company-ID required")
    b = request.get_json(silent=True) or {}
    if not b.get("channel_type") or not b.get("connector_type"):
        return err("channel_type and connector_type required")
    ch = ChannelAccount(company_id=cid, channel_type=b["channel_type"],
                        connector_type=b["connector_type"],
                        display_name=b.get("display_name"),
                        external_account_id=b.get("external_account_id"),
                        status=b.get("status", "pending"),
                        credentials=b.get("credentials") or {},
                        config=b.get("config") or {})
    db.session.add(ch); db.session.commit()
    return jsonify({"id": ch.id}), 201


# ---------- connector status (frontend-facing) ----------
STALE_HEARTBEAT_SECONDS = 60

@app.route("/api/connector-status", methods=["GET"])
def connector_status():
    cid = get_company_id()
    if not cid:
        return err("X-Company-ID required")
    chs = ChannelAccount.query.filter_by(company_id=cid).all()
    now = datetime.utcnow()
    out = []
    for ch in chs:
        seconds_ago = None
        if ch.last_seen_at:
            seconds_ago = int((now - ch.last_seen_at).total_seconds())
        if ch.last_seen_at is None:
            effective = "never_seen"
        elif seconds_ago is not None and seconds_ago > STALE_HEARTBEAT_SECONDS:
            effective = "stale"
        else:
            effective = ch.status or "unknown"
        out.append({
            "id": ch.id,
            "display_name": ch.display_name,
            "channel_type": ch.channel_type,
            "status": ch.status,
            "effective_status": effective,
            "last_seen_at": serialize_dt(ch.last_seen_at),
            "seconds_since_heartbeat": seconds_ago,
            "last_error": ch.last_error,
        })
    return jsonify({"channel_accounts": out})


# ---------- connector endpoints (X-Connector-Secret protected) ----------
@app.route("/api/connectors/heartbeat", methods=["POST"])
@require_connector_secret
def connector_heartbeat():
    b = request.get_json(silent=True) or {}
    chid = b.get("channel_account_id")
    if not chid:
        return err("channel_account_id required")
    ch = db.session.get(ChannelAccount, chid)
    if not ch:
        return err("channel account not found", 404)

    sent_status = b.get("status") or "online"
    metadata = b.get("metadata") or {}

    ch.status = sent_status
    ch.last_seen_at = datetime.utcnow()
    ch.last_error = metadata.get("last_error")

    hb = ConnectorHeartbeat(
        channel_account_id=chid,
        connector_id=b.get("connector_id"),
        connector_version=b.get("connector_version"),
        status=sent_status,
        metadata_json=metadata,
    )
    db.session.add(hb)
    db.session.commit()
    return jsonify({"received_at": serialize_dt(hb.last_heartbeat_at)})


@app.route("/api/connectors/inbound", methods=["POST"])
@require_connector_secret
def ingest_inbound():
    b = request.get_json(silent=True) or {}
    chid = b.get("channel_account_id")
    emid = b.get("external_message_id")
    # Phase 10: accept direction so phone-sent fromMe messages can be ingested as outbound.
    direction = b.get("direction", "inbound")
    if direction not in ("inbound", "outbound"):
        direction = "inbound"
    if not chid or not emid:
        return err("channel_account_id and external_message_id required")
    ch = db.session.get(ChannelAccount, chid)
    if not ch:
        return err("channel account not found", 404)
    existing = Message.query.filter_by(external_message_id=emid).first()
    if existing:
        return jsonify({"id": existing.id, "conversation_id": existing.conversation_id,
                        "deduped": True}), 200
    sxid = b.get("sender_external_id")
    etid = b.get("external_thread_id")
    # Phase 10.1: @lid privacy-mode contacts have no real phone -- key off external_handles instead.
    is_lid = bool(b.get("is_lid"))
    contact = None
    if sxid:
        if ch.channel_type == "whatsapp":
            if is_lid:
                contact = Contact.query.filter(
                    Contact.company_id == ch.company_id,
                    Contact.external_handles["whatsapp_lid"].astext == sxid,
                ).first()
            else:
                contact = Contact.query.filter_by(company_id=ch.company_id,
                                                  primary_phone=sxid).first()
        if not contact:
            if is_lid:
                contact = Contact(company_id=ch.company_id,
                                  display_name=b.get("sender_name") or "(unknown contact)",
                                  primary_phone=None,
                                  external_handles={"whatsapp_lid": sxid, ch.channel_type: sxid})
            else:
                contact = Contact(company_id=ch.company_id,
                                  display_name=b.get("sender_name") or sxid,
                                  primary_phone=sxid if ch.channel_type == "whatsapp" else None,
                                  external_handles={ch.channel_type: sxid})
            db.session.add(contact); db.session.flush()
        elif is_lid and direction == "inbound":
            # Auto-replace placeholder display_name once the real pushName arrives on first inbound.
            _new_name = b.get("sender_name")
            if _new_name and contact.display_name in ("(unknown contact)", sxid):
                contact.display_name = _new_name
                db.session.flush()
    # Phase 9F: group chat detection — synthetic "group Contact" carries the group subject
    group_subject = b.get("group_subject")
    is_group_chat = bool(etid and etid.endswith("@g.us"))
    conv = None
    if etid:
        conv = Conversation.query.filter_by(channel_account_id=chid,
                                            external_thread_id=etid).first()
    if not conv:
        if is_group_chat:
            group_contact = Contact(
                company_id=ch.company_id,
                display_name=group_subject or "WhatsApp Group",
                primary_phone=None,
                external_handles={"whatsapp_group": etid},
            )
            db.session.add(group_contact); db.session.flush()
            _conv_contact_id = group_contact.id
        else:
            _conv_contact_id = contact.id if contact else None
        conv = Conversation(company_id=ch.company_id, channel_account_id=chid,
                            contact_id=_conv_contact_id,
                            external_thread_id=etid, status="open")
        db.session.add(conv); db.session.flush()
    elif is_group_chat and group_subject and conv.contact_id:
        # Refresh synthetic group Contact display_name if the WhatsApp group subject changed.
        _gc = db.session.get(Contact, conv.contact_id)
        if _gc and isinstance(_gc.external_handles, dict) and _gc.external_handles.get("whatsapp_group") == etid:
            if _gc.display_name != group_subject:
                _gc.display_name = group_subject
                db.session.flush()
    pt = b.get("platform_timestamp"); platform_timestamp = None
    if pt is not None:
        try:
            if isinstance(pt, (int, float)):
                if pt > 10_000_000_000:
                    pt = pt / 1000.0
                platform_timestamp = datetime.utcfromtimestamp(pt)
            elif isinstance(pt, str):
                platform_timestamp = datetime.fromisoformat(pt.replace("Z", "+00:00"))
        except Exception:
            platform_timestamp = None
    qmid = None
    qext = b.get("quoted_external_id")
    if qext:
        qm = Message.query.filter_by(conversation_id=conv.id,
                                     external_message_id=qext).first()
        if qm:
            qmid = qm.id
    # Phase 10: honor direction so phone-sent (fromMe) messages land as outbound.
    msg = Message(conversation_id=conv.id, direction=direction,
                  message_type=b.get("message_type", "text"),
                  text_content=b.get("text"),
                  sender_type=("user" if direction == "outbound" else "contact"),
                  sender_contact_id=(None if direction == "outbound" else (contact.id if contact else None)),
                  sender_external_id=sxid, external_message_id=emid,
                  quoted_message_id=qmid, platform_timestamp=platform_timestamp,
                  raw_payload=b.get("raw_payload"))
    db.session.add(msg); db.session.flush()
    for a in (b.get("attachments") or []):
        db.session.add(MessageAttachment(
            message_id=msg.id, attachment_type=a.get("attachment_type"),
            file_url=a.get("file_url"), file_name=a.get("file_name"),
            file_size=a.get("file_size"), mime_type=a.get("mime_type"),
            duration_seconds=a.get("duration_seconds"),
            width=a.get("width"), height=a.get("height"),
            thumbnail_url=a.get("thumbnail_url"),
            external_media_id=a.get("external_media_id")))
    conv.last_message_at = msg.created_at
    conv.last_message_preview = (msg.text_content or "[" + (msg.message_type or "media") + "]")[:500]
    conv.unread_count = (conv.unread_count or 0) + 1
    db.session.commit()
    return jsonify({"id": msg.id, "conversation_id": conv.id,
                    "contact_id": contact.id if contact else None,
                    "deduped": False}), 201


@app.route("/api/outbound-queue/poll", methods=["POST"])
@require_connector_secret
def poll_outbound_queue():
    """Lazy cleanup: stuck-processing items (>5min) get reset before this poll."""
    cleanup_stuck_queue_items()
    b = request.get_json(silent=True) or {}
    chid = b.get("channel_account_id")
    cnid = b.get("connector_id", "unknown")
    try:
        limit = min(int(b.get("limit", 10)), 50)
    except (TypeError, ValueError):
        limit = 10
    if not chid:
        return err("channel_account_id required")
    items = OutboundMessageQueue.query.filter_by(
        channel_account_id=chid, status="queued"
    ).order_by(OutboundMessageQueue.created_at).limit(limit).all()
    claimed = []
    now = datetime.utcnow()
    for it in items:
        it.status = "processing"; it.locked_at = now; it.locked_by = cnid
        it.attempts = (it.attempts or 0) + 1
        claimed.append({"id": it.id, "conversation_id": it.conversation_id,
                        "channel_account_id": it.channel_account_id,
                        "payload": it.payload, "attempts": it.attempts})
    db.session.commit()
    return jsonify({"items": claimed})


@app.route("/api/outbound-queue/<queue_id>", methods=["PATCH"])
@require_connector_secret
def update_queue_item(queue_id):
    item = db.session.get(OutboundMessageQueue, queue_id)
    if not item:
        return err("not found", 404)
    b = request.get_json(silent=True) or {}
    ns = b.get("status")
    if ns == "sent":
        item.status = "sent"
        item.sent_at = datetime.utcnow()
        item.external_message_id = b.get("external_message_id")
        p = item.payload or {}
        msg = Message(conversation_id=item.conversation_id, direction="outbound",
                      message_type=p.get("message_type", "text"),
                      text_content=p.get("text"), sender_type="user",
                      sender_user_id=item.created_by_user_id,
                      external_message_id=item.external_message_id,
                      platform_timestamp=item.sent_at,
                      raw_payload=b.get("raw_payload"))
        db.session.add(msg); db.session.flush()
        item.message_id = msg.id
        for a in (p.get("attachments") or []):
            db.session.add(MessageAttachment(
                message_id=msg.id, attachment_type=a.get("attachment_type"),
                file_url=a.get("file_url"), file_name=a.get("file_name"),
                file_size=a.get("file_size"), mime_type=a.get("mime_type"),
                duration_seconds=a.get("duration_seconds"),
                thumbnail_url=a.get("thumbnail_url")))
        conv = db.session.get(Conversation, item.conversation_id)
        if conv:
            conv.last_message_at = msg.created_at
            conv.last_message_preview = (msg.text_content or "[" + (msg.message_type or "media") + "]")[:500]
    elif ns == "failed":
        if (item.attempts or 0) >= (item.max_attempts or 3):
            item.status = "failed"
        else:
            item.status = "queued"; item.locked_at = None; item.locked_by = None
        item.error_message = b.get("error_message")
    elif ns == "cancelled":
        item.status = "cancelled"
    else:
        return err("status must be one of sent | failed | cancelled")
    db.session.commit()
    return jsonify({"id": item.id, "status": item.status, "attempts": item.attempts})


# ---------- admin ----------
@app.route("/api/admin/queue-cleanup", methods=["POST"])
def admin_queue_cleanup():
    return jsonify(cleanup_stuck_queue_items())


# ---------- index + health ----------
INDEX_HTML = ('<!doctype html><html><head><meta charset="utf-8">'
              '<title>Ohabai Pipeline</title>'
              '<style>body{font-family:-apple-system,sans-serif;max-width:880px;'
              'margin:48px auto;padding:0 24px;color:#1a1a1a;line-height:1.5}'
              'h1{font-weight:600;margin-bottom:4px}.sub{color:#666;margin-top:0}'
              '.box{background:#f7f7f7;border:1px solid #eee;padding:18px 22px;'
              'border-radius:10px;margin:24px 0}'
              'code{background:#eee;padding:2px 6px;border-radius:4px;font-size:13px}'
              'ul{padding-left:20px}li{margin:6px 0}</style></head><body>'
              '<h1>Ohabai Pipeline</h1>'
              '<p class="sub">Backend - unified omnichannel inbox CRM</p>'
              '<h3>API</h3><ul>'
              '<li><code>GET /api/conversations</code> (X-Company-ID)</li>'
              '<li><code>GET /api/conversations/&lt;id&gt;/messages</code></li>'
              '<li><code>POST /api/conversations/&lt;id&gt;/send</code></li>'
              '<li><code>GET /api/connector-status</code></li>'
              '<li><code>POST /api/contacts</code> &middot; '
              '<code>PATCH /api/contacts/&lt;id&gt;</code></li>'
              '<li><code>POST /api/channel-accounts</code></li>'
              '<li><code>POST /api/connectors/heartbeat</code> (secret)</li>'
              '<li><code>POST /api/connectors/inbound</code> (secret)</li>'
              '<li><code>POST /api/outbound-queue/poll</code> (secret)</li>'
              '<li><code>PATCH /api/outbound-queue/&lt;id&gt;</code> (secret)</li>'
              '<li><code>POST /api/admin/queue-cleanup</code></li>'
              '</ul><p><a href="/api/health">/api/health</a></p>'
              '</body></html>')


@app.route("/")
def index(): return render_template_string(INDEX_HTML)


@app.route("/api/health")
def health(): return jsonify({"status": "ok", "service": "ohabai-pipeline"})


# === PHASE 8A START ===
# R2 attachment upload endpoint. Multipart in, returns {url, key, filename, mime_type, size_bytes}.

import os as _os_8a
import sys as _sys_8a
import uuid as _uuid_8a
from datetime import datetime as _dt_8a

try:
    import boto3 as _boto3_8a
    from botocore.config import Config as _BotoConfig_8a
except ImportError:
    _boto3_8a = None
    print("[8A] boto3 not available; /api/attachments/upload will fail until requirements installed", file=_sys_8a.stderr, flush=True)


_R2_BUCKET     = _os_8a.environ.get("R2_BUCKET_NAME", "")
_R2_ENDPOINT   = _os_8a.environ.get("R2_ENDPOINT_URL", "")
_R2_ACCESS_KEY = _os_8a.environ.get("R2_ACCESS_KEY_ID", "")
_R2_SECRET     = _os_8a.environ.get("R2_SECRET_ACCESS_KEY", "")
_R2_PUBLIC_URL = _os_8a.environ.get("R2_PUBLIC_URL", "").rstrip("/")


def _r2_client_8a():
    if _boto3_8a is None:
        raise RuntimeError("boto3 not installed")
    return _boto3_8a.client(
        "s3",
        endpoint_url=_R2_ENDPOINT,
        aws_access_key_id=_R2_ACCESS_KEY,
        aws_secret_access_key=_R2_SECRET,
        region_name="auto",
        config=_BotoConfig_8a(signature_version="s3v4"),
    )


def _r2_build_key_8a(company_id, channel_account_id, filename):
    """<company_id>/<channel_account_id>/<yyyy>/<mm>/<dd>/<uuid>-<sanitized_filename>"""
    today = _dt_8a.utcnow()
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in (filename or "file"))[:100]
    if not safe_name or safe_name in (".", ".."):
        safe_name = "file"
    return f"{company_id}/{channel_account_id or 'default'}/{today.year:04d}/{today.month:02d}/{today.day:02d}/{_uuid_8a.uuid4()}-{safe_name}"


@app.route("/api/attachments/upload", methods=["POST"])
def upload_attachment_8a():
    """Multipart upload to R2.
    Required form: file. Optional form: channel_account_id.
    Header: X-Company-ID required.
    Returns 201 {url, key, filename, mime_type, size_bytes}.
    """
    cid = get_company_id()
    if not cid:
        return err("X-Company-ID required")
    if not (_R2_BUCKET and _R2_ENDPOINT and _R2_ACCESS_KEY and _R2_SECRET):
        print("[r2] missing one or more R2_* env vars on Railway", file=_sys_8a.stderr, flush=True)
        return err("R2 not configured", 500)
    if "file" not in request.files:
        return err("file part required (multipart form)")
    f = request.files["file"]
    if not f or not f.filename:
        return err("empty file")
    channel_account_id = request.form.get("channel_account_id", "")
    body = f.read()
    if not body:
        return err("file is empty")
    if len(body) > 25 * 1024 * 1024:
        return err(f"file too large: {len(body)} bytes (max 25 MB)", 413)
    mime_type = f.mimetype or "application/octet-stream"
    key = _r2_build_key_8a(cid, channel_account_id, f.filename)
    try:
        _r2_client_8a().put_object(
            Bucket=_R2_BUCKET,
            Key=key,
            Body=body,
            ContentType=mime_type,
            Metadata={
                "company_id": str(cid),
                "channel_account_id": str(channel_account_id),
                "original_filename": (f.filename or "")[:200],
            },
        )
    except Exception as e:
        print(f"[r2] upload failed key={key}: {e}", file=_sys_8a.stderr, flush=True)
        return err(f"R2 upload failed: {e}", 502)
    public_url = f"{_R2_PUBLIC_URL}/{key}" if _R2_PUBLIC_URL else ""
    print(f"[r2] uploaded key={key} size={len(body)} mime={mime_type}", file=_sys_8a.stderr, flush=True)
    return jsonify({
        "url": public_url,
        "key": key,
        "filename": f.filename,
        "mime_type": mime_type,
        "size_bytes": len(body),
    }), 201
# === PHASE 8A END ===


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
