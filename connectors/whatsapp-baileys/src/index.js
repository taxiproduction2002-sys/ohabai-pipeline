import { config } from './config.js';
import { log } from './logger.js';
import { startSocket } from './socket.js';
import { handleInbound } from './inbound.js';
import { startHeartbeat } from './heartbeat.js';
import { startPolling } from './outbound.js';
import { startHealthServer } from './health.js';
import { state } from './state.js';

async function main() {
  log.info(
    {
      pipeline: config.PIPELINE_API_URL,
      channel: config.CHANNEL_ACCOUNT_ID,
      connector_id: config.CONNECTOR_ID,
      poll_interval_ms: config.POLL_INTERVAL_MS,
      node_env: process.env.NODE_ENV || 'development',
    },
    'Ohabai WhatsApp connector starting'
  );

  startHealthServer();
  startHeartbeat();
  await startSocket({ onMessage: async (msg) => handleInbound(msg) });
  startPolling();
}

let shuttingDown = false;
async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  log.info({ signal }, 'shutting down gracefully');
  state.connectionStatus = 'offline';
  try { state.threadCache.persist(); } catch {}
  setTimeout(() => process.exit(0), 3000);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

process.on('uncaughtException', (e) => {
  log.fatal({ err: e.message, stack: e.stack }, 'uncaught exception');
});

process.on('unhandledRejection', (e) => {
  log.error({ err: e?.message || String(e) }, 'unhandled rejection');
});

main().catch((e) => {
  log.fatal({ err: e.message, stack: e.stack }, 'fatal');
  process.exit(1);
});
