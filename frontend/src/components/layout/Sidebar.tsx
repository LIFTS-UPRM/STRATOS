"use client";

import Image from "next/image";
import type { McpToolGroupId } from "@/types/chat";
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

// ─── Data ─────────────────────────────────────────────────────
const TOOLS: {
  id: McpToolGroupId;
  label: string;
  Icon: () => JSX.Element;
}[] = [
  { id: "trajectory", label: "Trajectory", Icon: RouteIcon },
  { id: "weather", label: "Weather", Icon: CloudIcon },
  { id: "airspace", label: "Airspace Weather", Icon: TelemetryIcon },
];

type MissionStatus = "active" | "upcoming" | "completed";

const MISSIONS: { id: string; title: string; status: MissionStatus }[] = [
  { id: "m1", title: "ASCENT Sub-Scale",      status: "active" },
  { id: "m2", title: "ASCENT",                status: "upcoming" },
  { id: "m3", title: "Nexo",                  status: "completed" },
];

// ─── Toggle switch ─────────────────────────────────────────────
function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={"Toggle " + label}
      onClick={onChange}
      className={styles.toggle + (checked ? " " + styles.toggleOn : "")}
    >
      <span className={styles.toggleThumb} />
    </button>
  );
}

// ─── Component ────────────────────────────────────────────────
interface SidebarProps {
  isOpen: boolean;
  onToggle?: () => void;
  enabledToolGroups: Record<McpToolGroupId, boolean>;
  onToggleToolGroup: (id: McpToolGroupId) => void;
}

export default function Sidebar({
  isOpen,
  enabledToolGroups,
  onToggleToolGroup,
}: SidebarProps) {
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

        {/* Tools — per-MCP toggle rows */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionLabel}>Tools</span>
          </div>
          <div className={styles.sectionBody}>
            {TOOLS.map(({ id, label, Icon }) => {
              const on = enabledToolGroups[id];
              return (
                <div
                  key={id}
                  className={styles.toolRow + (on ? " " + styles.toolRowOn : "")}
                >
                  <span className={styles.toolIcon + (on ? " " + styles.toolIconOn : "")}>
                    <Icon />
                  </span>
                  <span className={styles.toolLabel + (on ? " " + styles.toolLabelOn : "")}>
                    {label}
                  </span>
                  <Toggle
                    checked={on}
                    onChange={() => onToggleToolGroup(id)}
                    label={label}
                  />
                </div>
              );
            })}
          </div>
        </section>

        {/* Missions */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionLabel}>Missions</span>
          </div>
          <div className={styles.sectionBody}>
            {MISSIONS.map((m) => (
              <button
                key={m.id}
                className={
                  styles.missionItem +
                  (m.status === "active" ? " " + styles.missionActive : "")
                }
              >
                <span className={styles.missionIcon}><RocketIcon /></span>
                <span className={styles.missionTitle}>{m.title}</span>
                <span className={styles.statusDot + " " + styles["status_" + m.status]} />
              </button>
            ))}
          </div>
        </section>

      </div>
    </aside>
  );
}
