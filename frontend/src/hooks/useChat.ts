import { useCallback, useEffect, useState } from "react";
import { api, ChatMessage, ChatReply } from "../api/client";

interface UseChatResult {
  messages: ChatMessage[];
  sending: boolean;
  error: string | null;
  lastReply: ChatReply | null;
  send: (content: string) => Promise<ChatReply | null>;
  refresh: () => Promise<void>;
}

/** Manages the Lead chat: load history on mount, send messages, refresh. */
export function useChat(projectId: string | null): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastReply, setLastReply] = useState<ChatReply | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      const history = await api.getChatHistory(projectId);
      setMessages(history);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const send = useCallback(
    async (content: string): Promise<ChatReply | null> => {
      if (!projectId) return null;
      setSending(true);
      setError(null);
      // Optimistic: append the user's message immediately.
      const optimistic: ChatMessage = {
        id: -Date.now(), // negative marker, replaced on refresh
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimistic]);
      try {
        const reply = await api.sendChat(projectId, content);
        setLastReply(reply);
        // Refresh history from server — picks up the real ids + lead reply.
        await refresh();
        return reply;
      } catch (e) {
        // Roll back optimistic append on error.
        setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        setError(e instanceof Error ? e.message : String(e));
        return null;
      } finally {
        setSending(false);
      }
    },
    [projectId, refresh],
  );

  return { messages, sending, error, lastReply, send, refresh };
}
