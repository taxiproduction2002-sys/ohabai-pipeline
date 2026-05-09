'use client';
import { useState } from 'react';
import { sendMessage } from '@/lib/api';

export default function Composer({ conversationId, onSent }) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);

  async function handleSend() {
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      await sendMessage(conversationId, text);
      setText('');
      if (onSent) await onSent();
    } catch (e) {
      alert(`Send failed: ${e.message}`);
    } finally {
      setSending(false);
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="composer">
      <input
        type="text"
        placeholder="Type a message..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKey}
        disabled={sending}
      />
      <button
        onClick={handleSend}
        disabled={!text.trim() || sending}
      >
        {sending ? '...' : 'Send'}
      </button>
    </div>
  );
}
