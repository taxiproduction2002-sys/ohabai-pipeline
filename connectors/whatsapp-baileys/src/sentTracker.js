// Phase 10: track msg_ids of messages we've sent via the outbound queue.
// When Baileys later fires a fromMe event for the same id, we suppress the
// ingest (backend already has the Message from the send-tasks PATCH).
// Phone-sent messages won't be in this set -- they get ingested as outbound.

const _sent = new Set();
const _TTL_MS = 5 * 60 * 1000;

export function markSent(id) {
  if (!id) return;
  _sent.add(id);
  setTimeout(() => _sent.delete(id), _TTL_MS);
}

export function consumeSent(id) {
  if (!id) return false;
  const had = _sent.has(id);
  if (had) _sent.delete(id);
  return had;
}
