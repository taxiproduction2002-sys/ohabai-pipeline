const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:5001';

function getCompanyId() {
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem('ohabai_company_id');
    if (stored) return stored;
  }
  return process.env.NEXT_PUBLIC_COMPANY_ID || '';
}

async function api(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'X-Company-ID': getCompanyId(),
    ...(options.headers || {}),
  };
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API ${res.status} ${path}: ${text || res.statusText}`);
  }
  return res.json();
}

export const fetchConversations = () => api('/api/conversations');
export const fetchMessages = (id) =>
  api(`/api/conversations/${id}/messages`);
export const sendMessage = (id, text) =>
  api(`/api/conversations/${id}/send`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
export const fetchConnectorStatus = () => api('/api/connector-status');
