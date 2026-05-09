import { config } from './config.js';
import { log } from './logger.js';
import { startSocket } from './socket.js';
import { handleInbound } from './inbound.js';
import { startHeartbeat } from './heartbeat.js';
import { startPolling } from './outbound.js';

async function main() {
  log.info(
    {
      pipeline: config.PIPELINE_API_URL,
      channel: config.CHANNEL_ACCOUNT_ID,
      connector_id: config.CONNECTOR_ID,
      poll_interval_ms: config.POLL_INTERVAL_MS,
    },
    'Ohabai WhatsApp connector starting'
  );

  startHeartbeat();

  await startSocket({
    onMessage: async (msg) => handleInbound(msg),
  });

  startPolling();
}

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
