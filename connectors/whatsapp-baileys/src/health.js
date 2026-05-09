import http from 'http';
import { config } from './config.js';
import { state } from './state.js';
import { log } from './logger.js';

export function startHealthServer() {
  const server = http.createServer((req, res) => {
    if (req.url === '/health') {
      const healthy = state.connectionStatus === 'online';
      const body = {
        status: healthy ? 'ok' : 'degraded',
        connection_status: state.connectionStatus,
        last_error: state.lastError,
        reconnect_attempts: state.reconnectAttempts,
        thread_cache_size: state.threadCache.size,
        connector_id: config.CONNECTOR_ID,
        connector_version: config.CONNECTOR_VERSION,
        uptime_seconds: Math.round((Date.now() - state.startedAt) / 1000),
      };
      res.writeHead(healthy ? 200 : 503, {
        'Content-Type': 'application/json',
      });
      res.end(JSON.stringify(body));
      return;
    }
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'not found' }));
  });

  server.on('error', (err) => {
    log.error({ err: err.message }, 'health server error');
  });

  server.listen(config.HEALTH_PORT, () => {
    log.info({ port: config.HEALTH_PORT }, 'health server listening');
  });

  return server;
}
