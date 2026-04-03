"use client";

import { useState, useCallback } from "react";
import type { McpToolGroupId, Message } from "@/types/chat";
import { sendMessage } from "@/lib/chatApi";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import MessageList from "@/components/chat/MessageList";
import InputBar from "@/components/chat/InputBar";
import styles from "./ChatPage.module.css";

const SUGGESTIONS = [
  "Run trajectory analysis with current wind data",
  "Show active NOTAMs for the launch region",
  "What's our go/no-go status for the launch window?",
];

const DEFAULT_TOOL_GROUPS: Record<McpToolGroupId, boolean> = {
  trajectory: true,
  weather: true,
  airspace: true,
};

const TRAJECTORY_REQUEST_PATTERN =
  /\b(trajectory|landing|burst|ascent|descent|simulation|simulate|monte carlo|nozzle lift|balloon)\b/i;

function needsTrajectoryMcp(content: string): boolean {
  return TRAJECTORY_REQUEST_PATTERN.test(content);
}

let messageCounter = 0;
function generateId(): string {
  return `msg-${++messageCounter}-${Date.now()}`;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [enabledToolGroups, setEnabledToolGroups] = useState(DEFAULT_TOOL_GROUPS);

  const handleSend = useCallback(async (content: string) => {
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content,
      createdAt: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    const selectedToolGroups = Object.entries(enabledToolGroups)
      .filter(([, enabled]) => enabled)
      .map(([id]) => id as McpToolGroupId);

    if (!enabledToolGroups.trajectory && needsTrajectoryMcp(content)) {
      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content:
          "Please enable the Trajectory MCP in the sidebar to run trajectory simulations and landing predictions.",
        createdAt: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
      setIsLoading(false);
      return;
    }

    try {
      const data = await sendMessage(content, messages, selectedToolGroups);
      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: data.response,
        createdAt: new Date(),
        toolCalls: data.tool_calls,
        trajectoryArtifact: data.trajectory_artifact,
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
  }, [enabledToolGroups, messages]);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarOpen((prev) => !prev);
  }, []);

  const handleToggleToolGroup = useCallback((id: McpToolGroupId) => {
    setEnabledToolGroups((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  return (
    <div className={styles.appShell}>
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={handleToggleSidebar}
        enabledToolGroups={enabledToolGroups}
        onToggleToolGroup={handleToggleToolGroup}
      />

      <div className={styles.mainArea}>
        <Header
          onToggleSidebar={handleToggleSidebar}
          isSidebarOpen={isSidebarOpen}
        />

        <main className={styles.chatMain}>
          <MessageList
            messages={messages}
            isLoading={isLoading}
          />
          <InputBar
            onSend={handleSend}
            disabled={isLoading}
            suggestions={messages.length === 0 && !isLoading ? SUGGESTIONS : undefined}
          />
        </main>
      </div>
    </div>
  );
}
