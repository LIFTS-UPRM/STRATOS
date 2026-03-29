"use client";

import { useEffect, useRef } from "react";
import type { Message } from "@/types/chat";
import styles from "./MessageList.module.css";

interface MessageListProps {
  messages: Message[];
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`${styles.messageRow} ${isUser ? styles.userRow : styles.assistantRow}`}>
      {!isUser && (
        <div className={styles.avatar} aria-label="STRATOS AI">
          ⬡
        </div>
      )}

      <div className={`${styles.bubble} ${isUser ? styles.userBubble : styles.assistantBubble}`}>
        <p className={styles.messageText}>{message.content}</p>
        <span className={styles.timestamp}>{formatTime(message.createdAt)}</span>
      </div>

      {isUser && (
        <div className={`${styles.avatar} ${styles.userAvatar}`} aria-label="You">
          ◉
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className={styles.emptyState}>
      <span className={styles.emptyIcon}>⬡</span>
      <h2 className={styles.emptyTitle}>STRATOS Mission Chat</h2>
      <p className={styles.emptySubtitle}>
        Ask anything about telemetry, trajectory, or flight data.
      </p>
    </div>
  );
}

export default function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className={styles.container}>
      {messages.length === 0 ? (
        <EmptyState />
      ) : (
        <div className={styles.messageList}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
