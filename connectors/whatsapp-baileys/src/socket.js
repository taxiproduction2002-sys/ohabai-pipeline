import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
  makeCacheableSignalKeyStore,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import qrcode from 'qrcode-terminal';
import pino from 'pino';
import path from 'path';
import fs from 'fs/promises';
import { config } from './config.js';
import { log } from './logger.js';
import { state } from './state.js';

const baileysLogger = pino({ level: 'silent' });

let sock = null;
let reconnectTimer = null;

export function getSocket() {
  return sock;
}

function reconnectDelayMs(attempts) {
  const base = 2000;
  const max = 60000;
  return Math.min(base * Math.pow(2, attempts - 1), max);
}

export async function startSocket(handlers) {
  const authDir = path.resolve(`./auth/${config.CHANNEL_ACCOUNT_ID}`);
  await fs.mkdir(authDir, { recursive: true });

  const { state: authState, saveCreds } = await useMultiFileAuthState(authDir);
  const { version, isLatest } = await fetchLatestBaileysVersion();
  log.info({ version: version.join('.'), isLatest }, 'Baileys version');

  sock = makeWASocket({
    version,
    auth: {
      creds: authState.creds,
      keys: makeCacheableSignalKeyStore(authState.keys, baileysLogger),
    },
    printQRInTerminal: false,
    browser: Browsers.macOS('Desktop'),
    syncFullHistory: false,
    markOnlineOnConnect: false,
    logger: baileysLogger,
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      log.info('QR received - scan in WhatsApp -> Linked Devices');
      qrcode.generate(qr, { small: true });
      state.connectionStatus = 'reconnecting';
    }

    if (connection === 'connecting') {
      state.connectionStatus = 'reconnecting';
    }

    if (connection === 'open') {
      const me = sock.user?.id;
      log.info({ me, attempts: state.reconnectAttempts }, 'connection open');
      state.connectionStatus = 'online';
      state.lastError = null;
      state.reconnectAttempts = 0;
    }

    if (connection === 'close') {
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode;
      const isLoggedOut = statusCode === DisconnectReason.loggedOut;
      const errMsg =
        lastDisconnect?.error?.message ||
        `disconnect statusCode=${statusCode}`;

      log.warn({ statusCode, isLoggedOut, err: errMsg }, 'connection closed');
      state.lastError = errMsg;

      if (isLoggedOut) {
        state.connectionStatus = 'offline';
        log.error('logged out - clearing auth, restart required');
        try {
          await fs.rm(authDir, { recursive: true, force: true });
        } catch {}
        process.exit(1);
      } else {
        state.connectionStatus = 'reconnecting';
        state.reconnectAttempts += 1;
        const delay = reconnectDelayMs(state.reconnectAttempts);
        log.warn(
          { attempts: state.reconnectAttempts, delay_ms: delay },
          'scheduling reconnect'
        );
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => {
          startSocket(handlers).catch((e) =>
            log.error({ err: e.message }, 'reconnect failed')
          );
        }, delay);
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;
    for (const msg of messages) {
      try {
        await handlers.onMessage(msg, sock);
      } catch (e) {
        log.error(
          { err: e.message, stack: e.stack },
          'message handler error'
        );
      }
    }
  });

  return sock;
}
