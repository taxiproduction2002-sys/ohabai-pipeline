import { downloadMediaMessage } from '@whiskeysockets/baileys';
import pino from 'pino';
import { config } from './config.js';
import { log } from './logger.js';
import { api } from './api.js';
import { state } from './state.js';
import { uploadToR2, buildR2Key, inferExtension } from './r2.js';
import { getSocket } from './socket.js';
import { consumeSent } from './sentTracker.js';

const downloadLog = pino({ level: 'silent' });

// Phase 9F: cache WhatsApp group subjects so we don't fetch metadata every message.
const _groupSubjectCache = new Map();
const _GROUP_SUBJECT_TTL_MS = 30 * 60 * 1000;

async function getGroupSubject(jid) {
  if (!jid || !jid.endsWith('@g.us')) return null;
  const cached = _groupSubjectCache.get(jid);
  if (cached && (Date.now() - cached.fetchedAt) < _GROUP_SUBJECT_TTL_MS) {
    return cached.subject;
  }
  try {
    const sock = getSocket();
    if (!sock) return cached?.subject || null;
    const meta = await sock.groupMetadata(jid);
    const subj = meta?.subject || null;
    _groupSubjectCache.set(jid, { subject: subj, fetchedAt: Date.now() });
    return subj;
  } catch (e) {
    log.warn({ err: e.message, jid }, 'groupMetadata fetch failed');
    return cached?.subject || null;
  }
}

function jidToPhone(jid) {
  if (!jid) return null;
  return jid.split('@')[0].split(':')[0];
}

function isGroup(jid) {
  return Boolean(jid && jid.endsWith('@g.us'));
}

function preview(text, type) {
  if (!text) return `[${type}]`;
  return text.length > 30 ? text.slice(0, 30) + '...' : text;
}

function extractContent(msg) {
  const m = msg.message;
  if (!m) return null;
  const inner =
    m.ephemeralMessage?.message ||
    m.viewOnceMessage?.message ||
    m.viewOnceMessageV2?.message ||
    m;

  let text = null;
  let messageType = 'text';
  let attachment = null;

  if (inner.conversation) {
    text = inner.conversation;
  } else if (inner.extendedTextMessage?.text) {
    text = inner.extendedTextMessage.text;
  } else if (inner.imageMessage) {
    messageType = 'image';
    text = inner.imageMessage.caption || null;
    attachment = {
      attachment_type: 'image',
      mime_type: inner.imageMessage.mimetype,
      file_size: inner.imageMessage.fileLength ? Number(inner.imageMessage.fileLength) : null,
      width: inner.imageMessage.width,
      height: inner.imageMessage.height,
    };
  } else if (inner.videoMessage) {
    messageType = 'video';
    text = inner.videoMessage.caption || null;
    attachment = {
      attachment_type: 'video',
      mime_type: inner.videoMessage.mimetype,
      duration_seconds: inner.videoMessage.seconds,
      file_size: inner.videoMessage.fileLength ? Number(inner.videoMessage.fileLength) : null,
    };
  } else if (inner.audioMessage) {
    messageType = inner.audioMessage.ptt ? 'voice' : 'audio';
    attachment = {
      attachment_type: messageType,
      mime_type: inner.audioMessage.mimetype,
      duration_seconds: inner.audioMessage.seconds,
      file_size: inner.audioMessage.fileLength ? Number(inner.audioMessage.fileLength) : null,
    };
  } else if (inner.documentMessage) {
    messageType = 'file';
    attachment = {
      attachment_type: 'file',
      mime_type: inner.documentMessage.mimetype,
      file_name: inner.documentMessage.fileName,
      file_size: inner.documentMessage.fileLength ? Number(inner.documentMessage.fileLength) : null,
    };
  } else if (inner.stickerMessage) {
    messageType = 'sticker';
    attachment = {
      attachment_type: 'sticker',
      mime_type: inner.stickerMessage.mimetype,
    };
  } else {
    return null;
  }

  return { text, messageType, attachment };
}

async function downloadAndUploadMedia(msg, attachment) {
  const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger: downloadLog });
  const mime = (attachment.mime_type || '').split(';')[0].trim();
  const ext = inferExtension(mime, attachment.file_name);
  const baseName = attachment.file_name
    || `${attachment.attachment_type}-${(msg.key.id || 'media').slice(-12)}${ext}`;
  const key = buildR2Key(config.COMPANY_ID, config.CHANNEL_ACCOUNT_ID, baseName);
  const url = await uploadToR2(buf, key, mime || 'application/octet-stream');
  attachment.file_url = url;
  if (!attachment.file_size) attachment.file_size = buf.length;
  if (!attachment.file_name) attachment.file_name = baseName;
  return { size: buf.length, url };
}

export async function handleInbound(msg) {
  if (msg.key.remoteJid === 'status@broadcast') return;
  // Phase 10: don't drop fromMe blindly. Echoes of our own /crm sends are
  // tracked in sentTracker and skipped here. Anything else (phone-sent)
  // falls through and is ingested as outbound below.
  const fromMe = !!msg.key.fromMe;
  if (fromMe && consumeSent(msg.key.id)) {
    log.debug({ msg_id: msg.key.id }, 'fromMe echo for our own /crm send -- skipping');
    return;
  }

  const content = extractContent(msg);
  if (!content) {
    log.debug({ msg_id: msg.key.id }, 'unsupported message type, skipping');
    return;
  }

  const chatJid = msg.key.remoteJid;
  const group = isGroup(chatJid);
  // Phase 10: for outbound (fromMe), the conv's other party is the chat itself
  // for 1-on-1, and null for groups (synthetic group Contact carries the name).
  const senderJid = fromMe
    ? (group ? null : chatJid)
    : (group ? msg.key.participant : msg.key.remoteJid);
  const senderPhone = senderJid ? jidToPhone(senderJid) : null;

  // Phase 9F: fetch the WhatsApp group subject (cached) so backend can name the conv properly.
  let groupSubject = null;
  if (group) {
    groupSubject = await getGroupSubject(chatJid);
  }

  // Phase 8B: download media + upload to R2 (non-fatal — message still posts on failure)
  if (content.attachment) {
    try {
      const r = await downloadAndUploadMedia(msg, content.attachment);
      log.info(
        { msg_id: msg.key.id?.slice(-8), type: content.attachment.attachment_type, size: r.size },
        'media uploaded to R2'
      );
    } catch (e) {
      log.error(
        { err: e.message, msg_id: msg.key.id, type: content.attachment.attachment_type },
        'media upload failed; posting without file_url'
      );
    }
  }

  const payload = {
    channel_account_id: config.CHANNEL_ACCOUNT_ID,
    external_message_id: msg.key.id,
    external_thread_id: chatJid,
    sender_external_id: senderPhone,
    direction: fromMe ? 'outbound' : 'inbound',
    sender_name: fromMe ? null : (msg.pushName || senderPhone),
    group_subject: groupSubject,
    text: content.text,
    message_type: content.messageType,
    attachments: content.attachment ? [content.attachment] : [],
    platform_timestamp: msg.messageTimestamp ? Number(msg.messageTimestamp) : null,
    raw_payload: {
      key: msg.key,
      pushName: msg.pushName,
      isGroup: group,
      messageStubType: msg.messageStubType,
    },
  };

  try {
    const res = await api.post('/api/connectors/inbound', payload);
    if (res.data?.conversation_id) {
      state.threadCache.set(res.data.conversation_id, chatJid);
      state.threadCache.persist();
    }
    log.info(
      {
        from: senderPhone,
        group,
        msg_id: msg.key.id?.slice(-8),
        type: content.messageType,
        preview: preview(content.text, content.messageType),
        deduped: res.data?.deduped || false,
      },
      'inbound'
    );
  } catch (e) {
    state.lastError = `inbound: ${e.message}`;
    log.error(
      { err: e.response?.data || e.message, msg_id: msg.key.id },
      'inbound POST failed'
    );
  }
}
