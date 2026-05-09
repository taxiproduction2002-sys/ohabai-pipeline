'use client';
import { useEffect, useState } from 'react';
import { fetchConnectorStatus } from '@/lib/api';

const STATUS_POLL_MS = 15000;

const LABELS = {
  online: 'online',
  reconnecting: 'reconnecting',
  offline: 'offline',
  stale: 'stale',
  never_seen: 'never seen',
  unknown: 'unknown',
  pending: 'pending',
  error: 'error',
};

export default function StatusBadge() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const data = await fetchConnectorStatus();
        if (cancelled) return;
        setStatus(data.channel_accounts?.[0] || null);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError(e.message);
      }
    }
    refresh();
    const interval = setInterval(refresh, STATUS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (error) {
    return (
      <span className="status-badge status-error" title={error}>
        ● error
      </span>
    );
  }
  if (!status) {
    return <span className="status-badge status-loading">● ...</span>;
  }

  const eff = status.effective_status || 'unknown';
  const label = LABELS[eff] || eff;

  const tipParts = [`status: ${label}`];
  if (status.last_seen_at) {
    const isoUtc =
      status.last_seen_at.includes('T') && !status.last_seen_at.endsWith('Z')
        ? status.last_seen_at + 'Z'
        : status.last_seen_at;
    tipParts.push(`last seen: ${new Date(isoUtc).toLocaleString()}`);
  } else {
    tipParts.push('last seen: never');
  }
  if (status.seconds_since_heartbeat != null) {
    tipParts.push(`${status.seconds_since_heartbeat}s ago`);
  }
  if (status.last_error) {
    tipParts.push(`error: ${status.last_error}`);
  }
  const title = tipParts.join('\n');

  return (
    <span className={`status-badge status-${eff}`} title={title}>
      ● {label}
    </span>
  );
}
