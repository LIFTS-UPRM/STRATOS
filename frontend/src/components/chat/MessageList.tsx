"use client";

import { useEffect, useRef } from "react";
import type { Message } from "@/types/chat";
import styles from "./MessageList.module.css";

// ─── Helpers ──────────────────────────────────────────────────
function formatUtcTime(date: Date): string {
  return (
    date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }) + " UTC"
  );
}

// ─── Message components ────────────────────────────────────────
function AssistantMessage({ message }: { message: Message }) {
  return (
    <div className={styles.assistantCard}>
      <div className={styles.assistantHeader}>
        <span className={styles.assistantLabel}>STRATOS AI</span>
        <span className={styles.assistantTime}>{formatUtcTime(message.createdAt)}</span>
      </div>
      <p className={styles.assistantText}>{message.content}</p>
    </div>
  );
}

function UserMessage({ message }: { message: Message }) {
  return (
    <div className={styles.userRow}>
      <div className={styles.userBubble}>
        <p className={styles.userText}>{message.content}</p>
      </div>
    </div>
  );
}

// ─── Typing indicator ─────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className={styles.assistantCard}>
      <div className={styles.assistantHeader}>
        <span className={styles.assistantLabel}>STRATOS AI</span>
      </div>
      <div className={styles.typingDots}>
        <span className={styles.dot} style={{ animationDelay: "0ms" }} />
        <span className={styles.dot} style={{ animationDelay: "160ms" }} />
        <span className={styles.dot} style={{ animationDelay: "320ms" }} />
      </div>
    </div>
  );
}

// ─── Empty state ───────────────────────────────────────────────
const SUGGESTIONS = [
  "Run trajectory analysis with current wind data",
  "Show active NOTAMs for the launch region",
  "What's our go/no-go status for the launch window?",
];

function EmptyState({ onSuggestion }: { onSuggestion?: (text: string) => void }) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyInner}>
        <p className={styles.emptyLabel}>STRATOS Mission Chat</p>
        <p className={styles.emptySubtitle}>
          Ask anything about telemetry, trajectory, or flight data.
        </p>
        {onSuggestion && (
          <div className={styles.suggestions}>
            {SUGGESTIONS.map((s) => (
              <button key={s} className={styles.suggestionChip} onClick={() => onSuggestion(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main ──────────────────────────────────────────────────────
interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
  onSuggestion?: (text: string) => void;
}

export default function MessageList({
  messages,
  isLoading = false,
  onSuggestion,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className={styles.container}>
      {messages.length === 0 && !isLoading ? (
        <EmptyState onSuggestion={onSuggestion} />
      ) : (
        <div className={styles.feed}>
          {messages.map((msg) =>
            msg.role === "user"
              ? <UserMessage key={msg.id} message={msg} />
              : <AssistantMessage key={msg.id} message={msg} />
          )}
          {isLoading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
