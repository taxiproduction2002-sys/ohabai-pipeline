"""Ohabai Pipeline Phase 1 schema. Connector-agnostic by design."""
from datetime import datetime
import uuid
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def gen_uuid(): return str(uuid.uuid4())


class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    settings = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    company_id = db.Column(db.String(36), db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    role = db.Column(db.String(50), default="member")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("company_id", "email", name="uq_user_company_email"),)


# Channel plug-in points (Phase 2+): connector_type in
# {whatsapp_cloud_api, instagram_graph, messenger_graph, custom_bridge}.
class ChannelAccount(db.Model):
    __tablename__ = "channel_accounts"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    company_id = db.Column(db.String(36), db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type = db.Column(db.String(50), nullable=False)
    connector_type = db.Column(db.String(50), nullable=False)
    display_name = db.Column(db.String(255))
    external_account_id = db.Column(db.String(255))
    status = db.Column(db.String(50), default="pending")
    credentials = db.Column(db.JSON, default=dict)
    config = db.Column(db.JSON, default=dict)
    last_synced_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Contact(db.Model):
    __tablename__ = "contacts"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    company_id = db.Column(db.String(36), db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name = db.Column(db.String(255))
    primary_phone = db.Column(db.String(50), index=True)
    primary_email = db.Column(db.String(255), index=True)
    profile_picture_url = db.Column(db.String(2000))
    notes = db.Column(db.Text)
    external_handles = db.Column(db.JSON, default=dict)  # {channel_type: handle}
    tags = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Conversation(db.Model):
    __tablename__ = "conversations"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    company_id = db.Column(db.String(36), db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_account_id = db.Column(db.String(36), db.ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = db.Column(db.String(36), db.ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    external_thread_id = db.Column(db.String(255), index=True)
    status = db.Column(db.String(50), default="open")
    assigned_user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    last_message_at = db.Column(db.DateTime, index=True)
    last_message_preview = db.Column(db.String(500))
    unread_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("channel_account_id", "external_thread_id", name="uq_conv_channel_thread"),)


class ConversationParticipant(db.Model):
    __tablename__ = "conversation_participants"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = db.Column(db.String(36), db.ForeignKey("contacts.id", ondelete="SET NULL"))
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    participant_type = db.Column(db.String(50))
    external_participant_id = db.Column(db.String(255))
    role = db.Column(db.String(50))
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    left_at = db.Column(db.DateTime)


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = db.Column(db.String(20), nullable=False)
    message_type = db.Column(db.String(50), default="text")
    text_content = db.Column(db.Text)
    sender_type = db.Column(db.String(50))
    sender_contact_id = db.Column(db.String(36), db.ForeignKey("contacts.id", ondelete="SET NULL"))
    sender_user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    sender_external_id = db.Column(db.String(255))
    external_message_id = db.Column(db.String(255), index=True)
    quoted_message_id = db.Column(db.String(36), db.ForeignKey("messages.id", ondelete="SET NULL"))
    platform_timestamp = db.Column(db.DateTime)
    raw_payload = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    __table_args__ = (db.UniqueConstraint("conversation_id", "external_message_id", name="uq_msg_conv_external"),)


class MessageAttachment(db.Model):
    __tablename__ = "message_attachments"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    message_id = db.Column(db.String(36), db.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    attachment_type = db.Column(db.String(50))
    file_url = db.Column(db.String(2000))
    file_name = db.Column(db.String(500))
    file_size = db.Column(db.BigInteger)
    mime_type = db.Column(db.String(100))
    duration_seconds = db.Column(db.Integer)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    thumbnail_url = db.Column(db.String(2000))
    external_media_id = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MessageDeliveryStatus(db.Model):
    __tablename__ = "message_delivery_status"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    message_id = db.Column(db.String(36), db.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(50))
    recipient_external_id = db.Column(db.String(255))
    error_code = db.Column(db.String(100))
    error_message = db.Column(db.Text)
    raw_payload = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIMemoryBlock(db.Model):
    __tablename__ = "ai_memory_blocks"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    company_id = db.Column(db.String(36), db.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    block_type = db.Column(db.String(50))
    title = db.Column(db.String(255))
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIReplySuggestion(db.Model):
    __tablename__ = "ai_reply_suggestions"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    triggering_message_id = db.Column(db.String(36), db.ForeignKey("messages.id", ondelete="SET NULL"))
    suggested_text = db.Column(db.Text, nullable=False)
    model_used = db.Column(db.String(100))
    confidence_score = db.Column(db.Float)
    status = db.Column(db.String(50), default="pending")
    used_at = db.Column(db.DateTime)
    used_by_user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    raw_response = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Outbound flow:
#   POST /api/conversations/<id>/send -> row inserted here (status=queued)
#   Connector polls /api/outbound-queue/poll (status=processing, locked_by)
#   Connector sends, PATCHes /api/outbound-queue/<id> (status=sent|failed)
#   On 'sent' a Message row (direction=outbound) is created.
class OutboundMessageQueue(db.Model):
    __tablename__ = "outbound_message_queue"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_account_id = db.Column(db.String(36), db.ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = db.Column(db.String(36), db.ForeignKey("messages.id", ondelete="SET NULL"))
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(50), default="queued", index=True)
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=3)
    next_attempt_at = db.Column(db.DateTime, default=datetime.utcnow)
    locked_at = db.Column(db.DateTime)
    locked_by = db.Column(db.String(255))
    error_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)
    external_message_id = db.Column(db.String(255))
    created_by_user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConnectorHeartbeat(db.Model):
    __tablename__ = "connector_heartbeats"
    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    channel_account_id = db.Column(db.String(36), db.ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    connector_id = db.Column(db.String(255))
    connector_version = db.Column(db.String(50))
    status = db.Column(db.String(50))
    last_heartbeat_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    metadata_json = db.Column(db.JSON, default=dict)  # 'metadata' is reserved by SQLAlchemy
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
