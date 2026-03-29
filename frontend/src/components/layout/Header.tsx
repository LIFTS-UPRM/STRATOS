"use client";

import styles from "./Header.module.css";

interface HeaderProps {
  onToggleSidebar: () => void;
  isSidebarOpen: boolean;
}

export default function Header({ onToggleSidebar, isSidebarOpen }: HeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <button
          className={styles.menuBtn}
          onClick={onToggleSidebar}
          aria-label={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
          title={isSidebarOpen ? "Close sidebar" : "Open sidebar"}
        >
          <span className={styles.menuIcon}>☰</span>
        </button>
        <span className={styles.pageTitle}>Mission Chat</span>
      </div>

      <div className={styles.center}>
        {/* Model / session info — placeholder */}
        <span className={styles.modelBadge}>STRATOS AI · v0.1</span>
      </div>

      <div className={styles.right}>
        {/* Placeholder nav actions */}
        <button className={styles.iconBtn} title="Mission overview">
          ◎
        </button>
        <button className={styles.iconBtn} title="User profile">
          ◉
        </button>
      </div>
    </header>
  );
}
