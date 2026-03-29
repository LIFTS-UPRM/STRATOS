"use client";

import { useState, useCallback } from "react";
import type { Message } from "@/types/chat";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import MessageList from "@/components/chat/MessageList";
import InputBar from "@/components/chat/InputBar";
import styles from "./ChatPage.module.css";

let messageCounter = 0;
function generateId(): string {
  return `msg-${++messageCounter}-${Date.now()}`;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  // `isLoading` is false-by-default; wire to actual backend when ready
  const [isLoading] = useState(false);

  const handleSend = useCallback((content: string) => {
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content,
      createdAt: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    // TODO: replace with real API call — stub echo for now
    setTimeout(() => {
      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: `[Backend not connected] Echo: "${content}"`,
        createdAt: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    }, 600);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarOpen((prev) => !prev);
  }, []);

  return (
    <div className={styles.appShell}>
      <Sidebar isOpen={isSidebarOpen} />

      <div className={styles.mainArea}>
        <Header
          onToggleSidebar={handleToggleSidebar}
          isSidebarOpen={isSidebarOpen}
        />

        <main className={styles.chatMain}>
          <MessageList messages={messages} />
          <InputBar onSend={handleSend} disabled={isLoading} />
        </main>
      </div>
    </div>
  );
}
