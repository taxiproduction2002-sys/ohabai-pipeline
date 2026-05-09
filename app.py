"""Ohabai Pipeline Phase 1 API. Connector-agnostic; connectors plug in via /api/connectors/* and /api/outbound-queue/*."""
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from sqlalchemy import desc
from models import (db, Company, User, ChannelAccount, Contact, Conversation,
                    ConversationParticipant, Message, MessageAttachment,
                    MessageDeliveryStatus, AIMemoryBlock, AIReplySuggestion,
                    OutboundMessageQueue, ConnectorHeartbeat)

app = Flask(__name__)
db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/ohabai_pipeline")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
db.init_app(app)
with app.app_context():
    db.create_all()


def get_company_id(): return request.headers.get("X-Company-ID")
def serialize_dt(dt): return dt.isoformat() if dt else None
def err(msg, status=400): return jsonify({"error": msg}), status


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
    out = []
    for m in msgs:
        atts = MessageAttachment.query.filter_by(message_id=m.id).all()
        out.append({"id": m.id, "direction": m.direction, "message_type": m.message_type,
                    "text_content": m.text_content, "sender_type": m.sender_type,
                    "sender_contact_id": m.sender_contact_id, "sender_user_id": m.sender_user_id,
                    "sender_external_id": m.sender_external_id,
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
    """Enqueue outbound. A connector polls /api/outbound-queue/poll to claim and send."""
    cid = get_company_id()
    conv = Conversation.query.filter_by(id=conv_id, company_id=cid).first()
    if not conv:
        return err("conversation not found", 404)
    b = request.get_json(silent=True) or {}
    text = b.get("text")
    atts = b.get("attachments") or []
    if not text and not atts:
        return err("text or attachments required")
    item = OutboundMessageQueue(
        conversation_id=conv.id, channel_account_id=conv.channel_account_id,
        payload={"text": text, "attachments": atts,
                 "quoted_external_id": b.get("quoted_external_id"),
                 "message_type": b.get("message_type", "text")},
        status="queued", created_by_user_id=b.get("user_id"))
    db.session.add(item); db.session.commit()
    return jsonify({"queue_id": item.id, "status": item.status,
                    "created_at": serialize_dt(item.created_at)}), 202


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


@app.route("/api/channel-accounts", methods=["POST"])
def create_channel_account():
    """Phase 2+ connector_type values: whatsapp_cloud_api, instagram_graph, messenger_graph, custom_bridge."""
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


@app.route("/api/connectors/heartbeat", methods=["POST"])
def connector_heartbeat():
    b = request.get_json(silent=True) or {}
    chid = b.get("channel_account_id")
    if not chid:
        return err("channel_account_id required")
    hb = ConnectorHeartbeat(channel_account_id=chid,
                            connector_id=b.get("connector_id"),
                            connector_version=b.get("connector_version"),
                            status=b.get("status", "healthy"),
                            metadata_json=b.get("metadata") or {})
    db.session.add(hb); db.session.commit()
    return jsonify({"received_at": serialize_dt(hb.last_heartbeat_at)})


@app.route("/api/connectors/inbound", methods=["POST"])
def ingest_inbound():
    """Ingest one inbound message. Dedup by external_message_id. Auto-creates contact and conversation."""
    b = request.get_json(silent=True) or {}
    chid = b.get("channel_account_id")
    emid = b.get("external_message_id")
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
    contact = None
    if sxid:
        if ch.channel_type == "whatsapp":
            contact = Contact.query.filter_by(company_id=ch.company_id,
                                              primary_phone=sxid).first()
        if not contact:
            contact = Contact(company_id=ch.company_id,
                              display_name=b.get("sender_name") or sxid,
                              primary_phone=sxid if ch.channel_type == "whatsapp" else None,
                              external_handles={ch.channel_type: sxid})
            db.session.add(contact); db.session.flush()
    conv = None
    if etid:
        conv = Conversation.query.filter_by(channel_account_id=chid,
                                            external_thread_id=etid).first()
    if not conv:
        conv = Conversation(company_id=ch.company_id, channel_account_id=chid,
                            contact_id=contact.id if contact else None,
                            external_thread_id=etid, status="open")
        db.session.add(conv); db.session.flush()
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
    msg = Message(conversation_id=conv.id, direction="inbound",
                  message_type=b.get("message_type", "text"),
                  text_content=b.get("text"), sender_type="contact",
                  sender_contact_id=contact.id if contact else None,
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
def poll_outbound_queue():
    """Connector atomically claims queued items; status flips to 'processing'."""
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
def update_queue_item(queue_id):
    """Connector reports back: sent | failed | cancelled. On 'sent', a Message row is created."""
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
              '<p class="sub">Phase 1 backend - unified omnichannel inbox CRM</p>'
              '<div class="box"><p>Channel connectors plug in via the endpoints below. '
              'No browser automation, no local bridges.</p></div>'
              '<h3>API</h3><ul>'
              '<li><code>GET /api/conversations</code> (X-Company-ID)</li>'
              '<li><code>GET /api/conversations/&lt;id&gt;/messages</code></li>'
              '<li><code>POST /api/conversations/&lt;id&gt;/send</code></li>'
              '<li><code>POST /api/contacts</code> &middot; '
              '<code>PATCH /api/contacts/&lt;id&gt;</code></li>'
              '<li><code>POST /api/channel-accounts</code></li>'
              '<li><code>POST /api/connectors/heartbeat</code></li>'
              '<li><code>POST /api/connectors/inbound</code></li>'
              '<li><code>POST /api/outbound-queue/poll</code></li>'
              '<li><code>PATCH /api/outbound-queue/&lt;id&gt;</code></li>'
              '</ul><p><a href="/api/health">/api/health</a></p>'
              '</body></html>')


@app.route("/")
def index(): return render_template_string(INDEX_HTML)


@app.route("/api/health")
def health(): return jsonify({"status": "ok", "service": "ohabai-pipeline", "phase": 1})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
