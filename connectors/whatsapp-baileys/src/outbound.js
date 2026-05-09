import { config } from './config.js';
import { log } from './logger.js';
import { api } from './api.js';
import { state } from './state.js';
import { getSocket } from './socket.js';

async function findThreadJid(conversationId) {
  if (state.threadCache.has(conversationId)) {
    return state.threadCache.get(conversationId);
  }
  // Fallback: hydrate cache from /api/conversations.
  try {
    const res = await api.get('/api/conversations', {
      params: {
        status: 'all',
        channel_account_id: config.CHANNEL_ACCOUNT_ID,
        limit: 200,
      },
      headers: { 'X-Company-ID': config.COMPANY_ID },
    });
    const list = res.data?.conversations || [];
    for (const c of list) {
      if (c.external_thread_id) {
        state.threadCache.set(c.id, c.external_thread_id);
      }
    }
    state.threadCache.persist();
    return state.threadCache.get(conversationId) || null;
  } catch (e) {
    log.warn({ err: e.message }, 'thread lookup failed');
    return null;
  }
}

async function sendItem(item) {
  const sock = getSocket();
  if (!sock) throw new Error('socket not connected');
  if (state.connectionStatus !== 'online') {
    throw new Error(`connection not ready (${state.connectionStatus})`);
  }

  const payload = item.payload || {};
  const text = payload.text;
  const messageType = payload.message_type || 'text';

  if (messageType !== 'text' || !text) {
    throw new Error(`only text messages supported in Phase 2 (got type=${messageType})`);
  }

  const jid = await findThreadJid(item.conversation_id);
  if (!jid) {
    throw new Error(`no thread JID resolved for conversation_id=${item.conversation_id}`);
  }

  const result = await sock.sendMessage(jid, { text });
  return { externalMessageId: result?.key?.id, jid };
}

export async function pollOnce() {
  if (state.connectionStatus !== 'online') return;

  let claimed = [];
  try {
    const res = await api.post('/api/outbound-queue/poll', {
      channel_account_id: config.CHANNEL_ACCOUNT_ID,
      connector_id: config.CONNECTOR_ID,
      limit: 5,
    });
    claimed = res.data?.items || [];
  } catch (e) {
    log.warn({ err: e.response?.data || e.message }, 'queue poll failed');
    return;
  }

  if (claimed.length === 0) return;
  log.info({ count: claimed.length }, 'claimed queue items');

  for (const item of claimed) {
    try {
      const { externalMessageId, jid } = await sendItem(item);
      await api.patch(`/api/outbound-queue/${item.id}`, {
        status: 'sent',
        external_message_id: externalMessageId,
      });
      const txt = item.payload?.text || '';
      log.info(
        {
          queue_id: item.id?.slice(-8),
          to: jid?.split('@')[0],
          msg_id: externalMessageId?.slice(-8),
          preview: txt.length > 30 ? txt.slice(0, 30) + '...' : txt,
        },
        'outbound sent'
      );
    } catch (e) {
      const errMsg = e.message || String(e);
      log.error(
        { err: errMsg, queue_id: item.id, attempts: item.attempts },
        'outbound send failed'
      );
      try {
        await api.patch(`/api/outbound-queue/${item.id}`, {
          status: 'failed',
          error_message: errMsg,
        });
      } catch (e2) {
        log.error(
          { err: e2.message, queue_id: item.id },
          'failed to PATCH failure status'
        );
      }
    }
  }
}

export function startPolling() {
  setInterval(() => {
    pollOnce().catch((e) =>
      log.error({ err: e.message }, 'pollOnce uncaught')
    );
  }, config.POLL_INTERVAL_MS);
  log.info({ interval_ms: config.POLL_INTERVAL_MS }, 'outbound poller started');
}
