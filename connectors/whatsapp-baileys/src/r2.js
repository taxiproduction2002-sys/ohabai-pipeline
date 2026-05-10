import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { config } from './config.js';

let _r2 = null;
function r2Client() {
  if (_r2) return _r2;
  if (!config.R2_ENDPOINT_URL || !config.R2_ACCESS_KEY_ID || !config.R2_SECRET_ACCESS_KEY) {
    throw new Error('R2 credentials missing');
  }
  _r2 = new S3Client({
    region: 'auto',
    endpoint: config.R2_ENDPOINT_URL,
    credentials: {
      accessKeyId: config.R2_ACCESS_KEY_ID,
      secretAccessKey: config.R2_SECRET_ACCESS_KEY,
    },
  });
  return _r2;
}

const MIME_TO_EXT = {
  'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
  'image/webp': '.webp', 'image/gif': '.gif', 'image/heic': '.heic',
  'video/mp4': '.mp4', 'video/webm': '.webm',
  'video/quicktime': '.mov', 'video/3gpp': '.3gp',
  'audio/ogg': '.ogg', 'audio/mpeg': '.mp3', 'audio/mp4': '.m4a',
  'audio/aac': '.aac', 'audio/wav': '.wav', 'audio/x-wav': '.wav',
  'application/pdf': '.pdf',
};

export function inferExtension(mimeType, fileName) {
  if (fileName) {
    const m = fileName.match(/\.[a-zA-Z0-9]{1,8}$/);
    if (m) return m[0].toLowerCase();
  }
  if (!mimeType) return '';
  const base = mimeType.split(';')[0].trim().toLowerCase();
  return MIME_TO_EXT[base] || '';
}

function sanitize(name) {
  return (name || 'file').replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 120) || 'file';
}

export function buildR2Key(companyId, channelAccountId, fileName) {
  const d = new Date();
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const uid = (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function')
    ? globalThis.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `${companyId}/${channelAccountId}/${yyyy}/${mm}/${dd}/${uid}-${sanitize(fileName)}`;
}

export async function uploadToR2(buffer, key, contentType) {
  if (!config.R2_BUCKET_NAME) throw new Error('R2_BUCKET_NAME not set');
  if (!config.R2_PUBLIC_URL) throw new Error('R2_PUBLIC_URL not set');
  await r2Client().send(new PutObjectCommand({
    Bucket: config.R2_BUCKET_NAME,
    Key: key,
    Body: buffer,
    ContentType: contentType || 'application/octet-stream',
  }));
  return `${config.R2_PUBLIC_URL}/${key}`;
}
