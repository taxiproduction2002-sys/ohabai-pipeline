import MessageBubble from './MessageBubble';
import Composer from './Composer';

export default function ChatThread({
  conversation,
  messages,
  onMessageSent,
}) {
  if (!conversation) {
    return (
      <main className="chat">
        <div className="empty-state">Select a conversation</div>
      </main>
    );
  }

  return (
    <main className="chat">
      <header className="chat-header">
        <div className="chat-title">
          {conversation.contact_name || 'Unknown'}
        </div>
        <div className="chat-subtitle">
          {conversation.external_thread_id}
        </div>
      </header>
      <div className="messages">
        {messages.length === 0 ? (
          <div className="empty-state">No messages yet</div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} message={m} />)
        )}
      </div>
      <Composer
        conversationId={conversation.id}
        onSent={onMessageSent}
      />
    </main>
  );
}
