"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { Message } from "@/types/chat";
import { MISSIONS } from "@/lib/missions";
import { sendMessage } from "@/lib/chatApi";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import MessageList from "@/components/chat/MessageList";
import InputBar from "@/components/chat/InputBar";
import styles from "./ChatPage.module.css";

const SUGGESTIONS = [
  "Run trajectory analysis with current wind data",
  "Show the no-flight zone for this balloon launch",
  "What's our go/no-go status for the launch window?",
];

let messageCounter = 0;
function generateId(): string {
  return `msg-${++messageCounter}-${Date.now()}`;
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [activeMissionId, setActiveMissionId] = useState(MISSIONS[0]?.id ?? "");
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [hasSubmittedSearch, setHasSubmittedSearch] = useState(false);
  const messagesRef = useRef<Message[]>([]);
  const requestGenerationRef = useRef(0);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!isSearchOpen) {
      return;
    }

    const focusFrame = window.requestAnimationFrame(() => {
      searchInputRef.current?.focus();
    });

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsSearchOpen(false);
        setSearchQuery("");
        setHasSubmittedSearch(false);
      }
    }

    document.addEventListener("keydown", handleEscape);

    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isSearchOpen]);

  const handleSend = useCallback(async (content: string) => {
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content,
      createdAt: new Date(),
    };
    const nextMessages = [...messagesRef.current, userMessage];
    const requestGeneration = ++requestGenerationRef.current;

    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    setIsLoading(true);

    try {
      const data = await sendMessage(content, nextMessages);
      if (requestGeneration !== requestGenerationRef.current) {
        return;
      }

      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: data.response,
        createdAt: new Date(),
        toolCalls: data.tool_calls,
        trajectoryArtifact: data.trajectory_artifact,
      };
      messagesRef.current = [...messagesRef.current, assistantMessage];
      setMessages(messagesRef.current);
    } catch (err) {
      if (requestGeneration !== requestGenerationRef.current) {
        return;
      }

      const errorText =
        err instanceof Error ? err.message : "An unexpected error occurred.";
      const errorMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: `⚠️ ${errorText}`,
        createdAt: new Date(),
      };
      messagesRef.current = [...messagesRef.current, errorMessage];
      setMessages(messagesRef.current);
    } finally {
      if (requestGeneration === requestGenerationRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  const handleNewChat = useCallback(() => {
    requestGenerationRef.current += 1;
    messagesRef.current = [];
    setMessages([]);
    setIsLoading(false);
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarOpen((prev) => !prev);
  }, []);

  const handleOpenSearch = useCallback(() => {
    setSearchQuery("");
    setHasSubmittedSearch(false);
    setIsSearchOpen(true);
  }, []);

  const handleCloseSearch = useCallback(() => {
    setIsSearchOpen(false);
    setSearchQuery("");
    setHasSubmittedSearch(false);
  }, []);

  const handleSearchSubmit = useCallback((event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!searchQuery.trim()) {
      return;
    }

    setHasSubmittedSearch(true);
  }, [searchQuery]);

  return (
    <div className={styles.appShell}>
      <Sidebar
        isOpen={isSidebarOpen}
        onNewChat={handleNewChat}
        onOpenSearch={handleOpenSearch}
        missions={MISSIONS}
        activeMissionId={activeMissionId}
      />

      <div className={styles.mainArea}>
        <Header
          onToggleSidebar={handleToggleSidebar}
          isSidebarOpen={isSidebarOpen}
          missions={MISSIONS}
          activeMissionId={activeMissionId}
          onSelectMission={setActiveMissionId}
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

      {isSearchOpen && (
        <div className={styles.searchOverlay}>
          <button
            className={styles.searchBackdrop}
            type="button"
            aria-label="Close search"
            onClick={handleCloseSearch}
          />
          <div
            className={styles.searchDialog}
            role="dialog"
            aria-modal="true"
            aria-labelledby="search-chats-title"
          >
            <div className={styles.searchHeader}>
              <div className={styles.searchHeading}>
                <h2 id="search-chats-title" className={styles.searchTitle}>Search chats</h2>
                <p className={styles.searchSubtitle}>Search history will appear here soon.</p>
              </div>
              <button
                className={styles.searchCloseBtn}
                type="button"
                onClick={handleCloseSearch}
                aria-label="Close search"
              >
                <CloseIcon />
              </button>
            </div>

            <form className={styles.searchForm} onSubmit={handleSearchSubmit}>
              <label className={styles.searchInputWrap}>
                <span className={styles.searchInputIcon}>
                  <SearchIcon />
                </span>
                <input
                  ref={searchInputRef}
                  className={styles.searchInput}
                  type="text"
                  value={searchQuery}
                  onChange={(event) => {
                    setSearchQuery(event.target.value);
                    setHasSubmittedSearch(false);
                  }}
                  placeholder="Search chats"
                  autoComplete="off"
                  aria-label="Search chats"
                />
              </label>
            </form>

            {hasSubmittedSearch ? (
              <p className={styles.searchEmptyState}>No results found</p>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
