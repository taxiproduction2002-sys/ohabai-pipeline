import { config } from './config.js';
import { log } from './logger.js';
import { api } from './api.js';
import { state } from './state.js';

const HEARTBEAT_INTERVAL_MS = 15000;

async function sendHeartbeat() {
  try {
    await api.post('/api/connectors/heartbeat', {
      channel_account_id: config.CHANNEL_ACCOUNT_ID,
      connector_id: config.CONNECTOR_ID,
      connector_version: config.CONNECTOR_VERSION,
      status: state.connectionStatus,
      metadata: {
        company_id: config.COMPANY_ID,
        connector_type: 'whatsapp_baileys',
        last_error: state.lastError,
        thread_cache_size: state.threadCache.size,
      },
    });
  } catch (e) {
    log.warn({ err: e.response?.data || e.message }, 'heartbeat failed');
  }
}

export function startHeartbeat() {
  sendHeartbeat();
  setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);
  log.info({ interval_ms: HEARTBEAT_INTERVAL_MS }, 'heartbeat started');
}
