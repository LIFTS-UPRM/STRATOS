"use client";

import { useState } from "react";
import styles from "./Header.module.css";

// ─── Constants ────────────────────────────────────────────────
const TABS = ["Chat", "Pre-Flight", "Mission Control", "Post-Flight"] as const;
type Tab = (typeof TABS)[number];

// ─── Icons ────────────────────────────────────────────────────
function SidebarToggleIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2.5" />
      <line x1="9" y1="3" x2="9" y2="21" />
      {isOpen
        ? <polyline points="6 9 4.5 12 6 15" />
        : <polyline points="12.5 9 14 12 12.5 15" />}
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function DotsVerticalIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="5"  r="1.2" fill="currentColor" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
      <circle cx="12" cy="19" r="1.2" fill="currentColor" />
    </svg>
  );
}

// ─── Component ────────────────────────────────────────────────
interface HeaderProps {
  projectName?: string;
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
}

export default function Header({
  projectName = "ASCENT Sub-Scale",
  onToggleSidebar,
  isSidebarOpen = true,
}: HeaderProps) {
  const [activeTab, setActiveTab] = useState<Tab>("Chat");

  return (
    <header className={styles.header}>
      {/* Left: sidebar toggle + project selector */}
      <div className={styles.left}>
        {onToggleSidebar && (
          <button
            className={styles.sidebarToggleBtn}
            onClick={onToggleSidebar}
            aria-label={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
            title={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
          >
            <SidebarToggleIcon isOpen={isSidebarOpen} />
          </button>
        )}
        <button className={styles.projectBtn} aria-label="Switch mission">
          <span className={styles.projectTitle}>{projectName}</span>
          <span className={styles.chevron}><ChevronDownIcon /></span>
        </button>
      </div>

      {/* Center: tab navigation */}
      <nav className={styles.tabs} aria-label="Mission views">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ""}`}
            onClick={() => setActiveTab(tab)}
            aria-current={activeTab === tab ? "page" : undefined}
          >
            {tab}
          </button>
        ))}
      </nav>

      {/* Right: user + actions */}
      <div className={styles.right}>
        <button className={styles.userAvatar} title="Profile" aria-label="Open profile">
          JS
        </button>
        <button className={styles.dotsBtn} aria-label="More options">
          <DotsVerticalIcon />
        </button>
      </div>
    </header>
  );
}
