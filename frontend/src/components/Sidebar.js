export default function Sidebar({
  conversations,
  selectedConvId,
  onSelect,
  error,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span>Inbox</span>
        <span className="counter">{conversations.length}</span>
      </div>
      {error && <div className="error">⚠ {error}</div>}
      <div className="conv-list">
        {conversations.length === 0 ? (
          <div className="empty-list">No conversations yet</div>
        ) : (
          conversations.map((conv) => (
            <ConversationItem
              key={conv.id}
              conversation={conv}
              isActive={conv.id === selectedConvId}
              onClick={() => onSelect(conv.id)}
            />
          ))
        )}
      </div>
    </aside>
  );
}

function ConversationItem({ conversation, isActive, onClick }) {
  return (
    <div
      className={`conv-item ${isActive ? 'active' : ''}`}
      onClick={onClick}
    >
      <div className="conv-row">
        <div className="conv-name">
          {conversation.contact_name || 'Unknown'}
        </div>
        {conversation.unread_count > 0 && (
          <span className="unread">{conversation.unread_count}</span>
        )}
      </div>
      <div className="conv-preview">
        {conversation.last_message_preview || '—'}
      </div>
      <div className="conv-time">
        {formatRelative(conversation.last_message_at)}
      </div>
    </div>
  );
}

function formatRelative(iso) {
  if (!iso) return '';
  const isoUtc =
    iso.includes('T') && !iso.endsWith('Z') ? iso + 'Z' : iso;
  const d = new Date(isoUtc);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
