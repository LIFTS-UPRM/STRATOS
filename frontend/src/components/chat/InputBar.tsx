"use client";

import { useState, useRef, KeyboardEvent } from "react";
import styles from "./InputBar.module.css";

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
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  // Auto-resize textarea
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
    setValue(el.value);
  };

  // Shift+Enter = newline, Enter alone = submit
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
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Message STRATOS… (Enter to send, Shift+Enter for newline)"
          rows={1}
          disabled={disabled}
          aria-label="Message input"
        />
        <button
          className={styles.sendBtn}
          onClick={handleSubmit}
          disabled={!canSend}
          aria-label="Send message"
          title="Send (Enter)"
        >
          ↑
        </button>
      </div>
      <p className={styles.hint}>
        STRATOS can make mistakes. Verify critical telemetry data independently.
      </p>
    </div>
  );
}
