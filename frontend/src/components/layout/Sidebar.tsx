"use client";

import styles from "./Sidebar.module.css";

interface SidebarProps {
  isOpen: boolean;
}

// Placeholder conversation history items
const PLACEHOLDER_CHATS = [
  { id: "1", title: "Flight trajectory analysis", date: "Today" },
  { id: "2", title: "Sensor calibration review", date: "Today" },
  { id: "3", title: "Altitude anomaly — Flight 04", date: "Yesterday" },
  { id: "4", title: "Telemetry stream debug", date: "Yesterday" },
  { id: "5", title: "Mission summary report", date: "Mar 25" },
];

export default function Sidebar({ isOpen }: SidebarProps) {
  return (
    <aside className={`${styles.sidebar} ${isOpen ? styles.open : styles.closed}`}>
      {/* Logo / Brand */}
      <div className={styles.brand}>
        <span className={styles.brandIcon}>⬡</span>
        <span className={styles.brandName}>STRATOS</span>
      </div>

      {/* New Chat */}
      <div className={styles.newChatWrapper}>
        <button className={styles.newChatBtn}>
          <span>+</span>
          New Chat
        </button>
      </div>

      {/* Chat History */}
      <nav className={styles.nav}>
        <p className={styles.sectionLabel}>Recent</p>
        <ul className={styles.chatList}>
          {PLACEHOLDER_CHATS.map((chat) => (
            <li key={chat.id} className={styles.chatItem}>
              <button className={styles.chatBtn}>
                <span className={styles.chatTitle}>{chat.title}</span>
                <span className={styles.chatDate}>{chat.date}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className={styles.sidebarFooter}>
        <button className={styles.footerBtn}>⚙ Settings</button>
      </div>
    </aside>
  );
}
