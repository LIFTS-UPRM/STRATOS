"use client";

import { useState, useCallback } from "react";
import type { Message } from "@/types/chat";
import { sendMessage } from "@/lib/chatApi";
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
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = useCallback(async (content: string) => {
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content,
      createdAt: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const data = await sendMessage(content);
      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: data.response,
        createdAt: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorText =
        err instanceof Error ? err.message : "An unexpected error occurred.";
      const errorMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: `⚠️ ${errorText}`,
        createdAt: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
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
