import fs from 'fs';
import path from 'path';
import { config } from './config.js';

class ThreadCache {
  constructor(filepath) {
    this.filepath = filepath;
    this.map = new Map();
    this.load();
  }
  load() {
    try {
      if (fs.existsSync(this.filepath)) {
        const raw = JSON.parse(fs.readFileSync(this.filepath, 'utf8'));
        this.map = new Map(Object.entries(raw));
      }
    } catch {
      this.map = new Map();
    }
  }
  persist() {
    try {
      fs.mkdirSync(path.dirname(this.filepath), { recursive: true });
      fs.writeFileSync(
        this.filepath,
        JSON.stringify(Object.fromEntries(this.map), null, 2)
      );
    } catch {}
  }
  has(k) { return this.map.has(k); }
  get(k) { return this.map.get(k); }
  set(k, v) { this.map.set(k, v); }
  get size() { return this.map.size; }
}

const cacheFile = path.resolve(`./cache/${config.CHANNEL_ACCOUNT_ID}/thread-cache.json`);

export const state = {
  connectionStatus: 'offline',
  lastError: null,
  threadCache: new ThreadCache(cacheFile),
  reconnectAttempts: 0,
  startedAt: Date.now(),
};
