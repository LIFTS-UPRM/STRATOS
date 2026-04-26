"use client";

import { useEffect, useRef, useState } from "react";
import type { Mission } from "@/types/mission";
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
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
  missions: Mission[];
  activeMissionId: string;
  onSelectMission: (missionId: string) => void;
}

export default function Header({
  onToggleSidebar,
  isSidebarOpen = true,
  missions,
  activeMissionId,
  onSelectMission,
}: HeaderProps) {
  const [activeTab, setActiveTab] = useState<Tab>("Chat");
  const [isMissionMenuOpen, setIsMissionMenuOpen] = useState(false);
  const missionMenuRef = useRef<HTMLDivElement | null>(null);
  const activeMission =
    missions.find((mission) => mission.id === activeMissionId) ?? missions[0];

  useEffect(() => {
    if (!isMissionMenuOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (!missionMenuRef.current?.contains(event.target as Node)) {
        setIsMissionMenuOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsMissionMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isMissionMenuOpen]);

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
        <div className={styles.missionSwitcher} ref={missionMenuRef}>
          <button
            className={styles.projectBtn}
            aria-label="Switch mission"
            aria-haspopup="menu"
            aria-expanded={isMissionMenuOpen}
            type="button"
            onClick={() => setIsMissionMenuOpen((open) => !open)}
          >
            <span className={styles.projectMeta}>
              <span className={styles.projectTitle}>{activeMission?.title ?? "Select mission"}</span>
            </span>
            <span className={styles.projectStatus}>{activeMission?.status ?? "upcoming"}</span>
            <span className={styles.chevron}><ChevronDownIcon /></span>
          </button>

          {isMissionMenuOpen && (
            <div className={styles.missionMenu} role="menu" aria-label="Mission switcher">
              {missions.map((mission) => {
                const isActive = mission.id === activeMissionId;

                return (
                  <button
                    key={mission.id}
                    className={`${styles.missionOption} ${isActive ? styles.missionOptionActive : ""}`}
                    type="button"
                    role="menuitemradio"
                    aria-checked={isActive}
                    onClick={() => {
                      onSelectMission(mission.id);
                      setIsMissionMenuOpen(false);
                    }}
                  >
                    <span className={styles.missionOptionText}>
                      <span className={styles.missionOptionTitle}>{mission.title}</span>
                      <span className={styles.missionOptionStatus}>{mission.status}</span>
                    </span>
                    <span
                      className={
                        styles.statusBadge +
                        " " +
                        styles["status_" + mission.status.replace("-", "_")]
                      }
                    >
                      {mission.status}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
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
