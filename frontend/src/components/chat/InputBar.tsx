"use client";

import { useState, useRef, KeyboardEvent } from "react";
import styles from "./InputBar.module.css";

// ─── Icons ────────────────────────────────────────────────────
function PlusIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5"  y1="12" x2="19" y2="12" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="5 12 12 5 19 12" />
    </svg>
  );
}

function PaperclipIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19
               a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function LoadingSpinner() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         className={styles.spinner}>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5"
              strokeLinecap="round" strokeDasharray="56.5" strokeDashoffset="14" />
    </svg>
  );
}

// ─── Component ────────────────────────────────────────────────
interface InputBarProps {
  onSend: (content: string) => void;
  disabled?: boolean;
}

export default function InputBar({ onSend, disabled = false }: InputBarProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
    setValue(el.value);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <div className={styles.wrapper}>
      <div className={styles.inputContainer}>
        {/* Left: context / attach */}
        <button className={styles.leftBtn} type="button"
                aria-label="Add attachment or context" title="Add context">
          <PlusIcon />
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything"
          rows={1}
          disabled={disabled}
          aria-label="Message input"
        />

        {/* Right: send + paperclip */}
        <div className={styles.rightActions}>
          <button
            className={`${styles.sendBtn} ${canSend ? styles.sendBtnActive : ""}`}
            onClick={handleSubmit}
            disabled={!canSend && !disabled}
            aria-label={disabled ? "Waiting for response" : "Send message"}
            title={disabled ? "Waiting…" : "Send (Enter)"}
            type="button"
          >
            {disabled ? <LoadingSpinner /> : <SendIcon />}
          </button>
          <button className={styles.attachBtn} type="button"
                  aria-label="Attach file" title="Attach file">
            <PaperclipIcon />
          </button>
        </div>
      </div>

      {/* Hint row */}
      <div className={styles.hintRow}>
        <p className={styles.hint}>
          STRATOS AI can make mistakes. Check important info.
        </p>
        <button className={styles.commandsBtn} type="button" aria-label="View slash commands">
          / commands
        </button>
      </div>
    </div>
  );
}
