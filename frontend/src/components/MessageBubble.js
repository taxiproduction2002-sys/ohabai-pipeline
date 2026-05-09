export default function MessageBubble({ message }) {
  const isOutbound = message.direction === 'outbound';
  const text = message.text_content ?? message.text ?? '';
  return (
    <div className={`bubble-row ${isOutbound ? 'outbound' : 'inbound'}`}>
      <div className={`bubble ${isOutbound ? 'outbound' : 'inbound'}`}>
        {message.quoted_message_id && (
          <div className="quoted-placeholder">
            ↩ replying to a message
          </div>
        )}
        <div className="bubble-text">
          {text || <i>(no text)</i>}
        </div>
        <div className="bubble-time">
          {formatTime(message.created_at)}
        </div>
      </div>
    </div>
  );
}

function formatTime(iso) {
  if (!iso) return '';
  const isoUtc =
    iso.includes('T') && !iso.endsWith('Z') ? iso + 'Z' : iso;
  const d = new Date(isoUtc);
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}
