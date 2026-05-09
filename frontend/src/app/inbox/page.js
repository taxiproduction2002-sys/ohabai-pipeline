'use client';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import ChatThread from '@/components/ChatThread';
import ContextPanel from '@/components/ContextPanel';
import { fetchConversations, fetchMessages } from '@/lib/api';

const POLL_INTERVAL_MS = 3000;

export default function InboxPage() {
  const router = useRouter();
  const [conversations, setConversations] = useState([]);
  const [selectedConvId, setSelectedConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const loggedIn = localStorage.getItem('ohabai_logged_in');
    if (!loggedIn) {
      router.replace('/login');
      return;
    }
    setAuthChecked(true);
  }, [router]);

  const refreshConversations = useCallback(async () => {
    try {
      const data = await fetchConversations();
      setConversations(data.conversations || []);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (!authChecked) return;
    refreshConversations();
    const interval = setInterval(refreshConversations, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [authChecked, refreshConversations]);

  const refreshMessages = useCallback(async () => {
    if (!selectedConvId) return;
    try {
      const data = await fetchMessages(selectedConvId);
      setMessages(data.messages || []);
    } catch (e) {
      setError(e.message);
    }
  }, [selectedConvId]);

  useEffect(() => {
    if (!authChecked) return;
    refreshMessages();
    if (!selectedConvId) return;
    const interval = setInterval(refreshMessages, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [authChecked, selectedConvId, refreshMessages]);

  if (!authChecked) return null;

  const selectedConv = conversations.find((c) => c.id === selectedConvId);

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        selectedConvId={selectedConvId}
        onSelect={setSelectedConvId}
        error={error}
      />
      <ChatThread
        conversation={selectedConv}
        messages={messages}
        onMessageSent={refreshMessages}
      />
      <ContextPanel conversation={selectedConv} />
    </div>
  );
}
