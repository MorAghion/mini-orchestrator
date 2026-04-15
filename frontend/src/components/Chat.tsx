import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage, ProjectStatus } from "../api/client";

interface Props {
  status: ProjectStatus;
  messages: ChatMessage[];
  sending: boolean;
  onSend: (content: string) => void;
  /** Label for the status banner under the header — "Shaping the brief" etc. */
  phaseLabel: string;
  /** If true, show a primary "Launch Stage 1" CTA above the composer. */
  readyToLaunch: boolean;
  onLaunch?: () => void;
  launching?: boolean;
}

export function Chat({
  status,
  messages,
  sending,
  onSend,
  phaseLabel,
  readyToLaunch,
  onLaunch,
  launching,
}: Props) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom when new messages land.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, sending]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = draft.trim();
    if (!v || sending) return;
    onSend(v);
    setDraft("");
  };

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter to send, Shift+Enter for newline
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const placeholder =
    status === "shaping"
      ? "Describe what you want to build…"
      : status === "stage1_done"
        ? "Ask about the docs or request a change…"
        : "Drop a note or ask the Lead…";

  return (
    <div className="chat">
      <div className="chat-header">
        <h3>Lead</h3>
        <span className="chat-phase">{phaseLabel}</span>
      </div>

      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            {status === "shaping"
              ? "Start by describing your project idea. The Lead will ask clarifying questions and help you shape a brief."
              : "No messages yet."}
          </div>
        )}
        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} />
        ))}
        {sending && (
          <div className="chat-bubble chat-bubble-lead chat-bubble-typing">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}
      </div>

      {readyToLaunch && onLaunch && (
        <div className="chat-launch-cta">
          <div className="launch-text">Brief is ready. Want to start Stage 1?</div>
          <button
            className="btn btn-primary"
            onClick={onLaunch}
            disabled={launching}
          >
            {launching ? "Launching…" : "Launch Stage 1 →"}
          </button>
        </div>
      )}

      <form className="chat-composer" onSubmit={handleSubmit}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          disabled={sending}
          rows={2}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={sending || !draft.trim()}
        >
          Send
        </button>
      </form>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`chat-bubble chat-bubble-${message.role}`}>
      <div className="chat-bubble-speaker">{isUser ? "You" : "Lead"}</div>
      <div className="chat-bubble-body">
        {isUser ? (
          message.content
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}
