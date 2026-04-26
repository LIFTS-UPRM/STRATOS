"use client";

import { useState } from "react";
import Image from "next/image";
import type { Mission } from "@/types/mission";
import styles from "./Sidebar.module.css";

// ─── Icons ────────────────────────────────────────────────────
function PencilIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function RocketIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
      <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
      <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
      <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
    </svg>
  );
}

function ChevronDownIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
      {isOpen ? null : <line x1="12" y1="15" x2="12" y2="15" />}
    </svg>
  );
}

// ─── Component ────────────────────────────────────────────────
interface SidebarProps {
  isOpen: boolean;
  onNewChat?: () => void;
  onOpenSearch?: () => void;
  missions: Mission[];
  activeMissionId: string;
}

export default function Sidebar({
  isOpen,
  onNewChat,
  onOpenSearch,
  missions,
  activeMissionId,
}: SidebarProps) {
  const [expandedMissionIds, setExpandedMissionIds] = useState<string[]>([missions[0]?.id ?? ""]);

  function toggleMissionFolder(missionId: string) {
    setExpandedMissionIds((current) =>
      current.includes(missionId)
        ? current.filter((id) => id !== missionId)
        : [...current, missionId]
    );
  }

  return (
    <aside className={styles.sidebar + (isOpen ? " " + styles.open : " " + styles.closed)}>
      {/* Brand row */}
      <div className={styles.brand}>
        <div className={styles.brandLeft}>
          <div className={styles.brandLogoWrap}>
            <Image src="/assets/STRATOS_LOGO_SVG/Color.svg" alt="STRATOS" width={22} height={22} priority />
          </div>
          <span className={styles.brandName}>STRATOS</span>
        </div>
      </div>

      {/* Quick actions */}
      <div className={styles.quickActions}>
        <button
          className={`${styles.quickBtn} ${styles.newChatBtn}`}
          type="button"
          onClick={onNewChat}
        >
          <span className={styles.quickIcon}><PencilIcon /></span>
          New chat
        </button>
        <button
          className={`${styles.quickBtn} ${styles.searchQuickBtn}`}
          type="button"
          onClick={onOpenSearch}
          aria-label="Search chats"
          title="Search chats"
          aria-haspopup="dialog"
        >
          <span className={styles.quickIcon}><SearchIcon /></span>
        </button>
      </div>

      {/* Scrollable body */}
      <div className={styles.scrollArea}>

        {/* Missions */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionLabel}>Missions</span>
          </div>
          <div className={styles.sectionBody}>
            {missions.map((mission) => {
              const isExpanded = expandedMissionIds.includes(mission.id);
              const isActive = mission.id === activeMissionId;

              return (
                <div key={mission.id} className={styles.missionFolder}>
                  <button
                    className={
                      styles.missionItem +
                      (isActive ? " " + styles.missionActive : "")
                    }
                    type="button"
                    onClick={() => toggleMissionFolder(mission.id)}
                    aria-expanded={isExpanded}
                  >
                    <span className={styles.missionIcon}><RocketIcon /></span>
                    <span className={styles.missionContent}>
                      <span className={styles.missionTitle}>{mission.title}</span>
                      <span className={styles.missionStatus}>{mission.status}</span>
                    </span>
                    <span
                      className={
                        styles.statusDot + " " + styles["status_" + mission.status.replace("-", "_")]
                      }
                    />
                    <span
                      className={
                        styles.missionChevron + (isExpanded ? " " + styles.missionChevronOpen : "")
                      }
                    >
                      <ChevronDownIcon isOpen={isExpanded} />
                    </span>
                  </button>

                  {isExpanded && (
                    <div className={styles.missionChats}>
                      <span className={styles.noChatsText}>No chats</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

      </div>
    </aside>
  );
}
