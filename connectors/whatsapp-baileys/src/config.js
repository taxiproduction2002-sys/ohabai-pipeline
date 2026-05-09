import 'dotenv/config';
import os from 'os';

function required(name) {
  const v = process.env[name];
  if (!v) {
    console.error(`Missing required env var: ${name}`);
    process.exit(1);
  }
  return v;
}

function intEnv(name, fallback) {
  const v = parseInt(process.env[name] || String(fallback), 10);
  return Number.isFinite(v) ? v : fallback;
}

export const config = {
  PIPELINE_API_URL: required('PIPELINE_API_URL').replace(/\/$/, ''),
  COMPANY_ID: required('COMPANY_ID'),
  CHANNEL_ACCOUNT_ID: required('CHANNEL_ACCOUNT_ID'),
  CONNECTOR_SECRET: process.env.CONNECTOR_SECRET || '',
  POLL_INTERVAL_MS: intEnv('POLL_INTERVAL_MS', 3000),
  HEARTBEAT_INTERVAL_MS: intEnv('HEARTBEAT_INTERVAL_MS', 15000),
  HEALTH_PORT: intEnv('HEALTH_PORT', 3000),
  CONNECTOR_ID: process.env.CONNECTOR_ID || `${os.hostname()}-${process.pid}`,
  CONNECTOR_VERSION: '1.1.0',
};
