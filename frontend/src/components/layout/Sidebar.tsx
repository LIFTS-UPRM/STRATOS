"use client";

import Image from "next/image";
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

function RouteIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="19" r="3" />
      <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
      <circle cx="18" cy="5" r="3" />
    </svg>
  );
}

function CloudIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
    </svg>
  );
}

function TelemetryIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

// ─── Data ─────────────────────────────────────────────────────
const TOOLS = [
  { id: "flight",    label: "Flight Planning", Icon: RouteIcon },
  { id: "weather",   label: "Weather Data",    Icon: CloudIcon },
  { id: "telemetry", label: "Telemetry",        Icon: TelemetryIcon },
];

const RECENTS: Record<string, { id: string; title: string; active?: boolean }[]> = {
  Today: [
    { id: "1", title: "Pre-flight Checklist Review", active: true },
    { id: "2", title: "NOTAM Analysis Region 4" },
    { id: "3", title: "Trajectory Optimization Run" },
  ],
  Yesterday: [
    { id: "4", title: "Post-flight Data Recovery" },
    { id: "5", title: "Wind Shear Analysis 03/24" },
    { id: "6", title: "Comms Check Frequency 7" },
  ],
  "Last Week": [
    { id: "7",  title: "Thermal Profile Sim B-12" },
    { id: "8",  title: "Landing Zone Recon Alpha" },
    { id: "9",  title: "Safety Protocol Update v3" },
    { id: "10", title: "GPS Drift Correction Log" },
  ],
};

// ─── Component ────────────────────────────────────────────────
interface SidebarProps {
  isOpen: boolean;
  onToggle?: () => void;
}

export default function Sidebar({ isOpen, onToggle }: SidebarProps) {
  return (
    <aside className={`${styles.sidebar} ${isOpen ? styles.open : styles.closed}`}>
      {/* Brand row */}
      <div className={styles.brand}>
        <div className={styles.brandLeft}>
          <div className={styles.brandLogoWrap}>
            <Image src="/logos/stratos-color.svg" alt="STRATOS" width={22} height={22} priority />
          </div>
          <span className={styles.brandName}>STRATOS</span>
        </div>
      </div>

      {/* Quick actions */}
      <div className={styles.quickActions}>
        <button className={styles.quickBtn}>
          <span className={styles.quickIcon}><PencilIcon /></span>
          New chat
        </button>
        <button className={styles.quickBtn}>
          <span className={styles.quickIcon}><SearchIcon /></span>
          Search chats
        </button>
      </div>

      {/* Scrollable body */}
      <div className={styles.scrollArea}>
        {/* Tools */}
        <section className={styles.section}>
          <p className={styles.sectionLabel}>Tools</p>
          {TOOLS.map(({ id, label, Icon }) => (
            <button key={id} className={styles.navItem}>
              <span className={styles.navIcon}><Icon /></span>
              <span className={styles.navLabel}>{label}</span>
            </button>
          ))}
        </section>

        {/* Recents */}
        <section className={styles.section}>
          <p className={styles.sectionLabel}>Recents</p>
          {Object.entries(RECENTS).map(([period, chats]) => (
            <div key={period} className={styles.timeGroup}>
              <p className={styles.timeLabel}>{period}</p>
              {chats.map((chat) => (
                <button
                  key={chat.id}
                  className={`${styles.chatItem} ${chat.active ? styles.chatItemActive : ""}`}
                >
                  <span className={styles.chatTitle}>{chat.title}</span>
                </button>
              ))}
            </div>
          ))}
        </section>
      </div>
    </aside>
  );
}
