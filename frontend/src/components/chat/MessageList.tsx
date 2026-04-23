"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import dynamic from "next/dynamic";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message, ToolCallRecord } from "@/types/chat";
import styles from "./MessageList.module.css";

const TrajectoryArtifactMap = dynamic(() => import("./TrajectoryArtifactMap"), {
  ssr: false,
  loading: () => (
    <div className={styles.trajectoryLoading}>Loading trajectory map...</div>
  ),
});

// ─── Helpers ───────────────────────────────────────────────────
function formatUtcTime(date: Date): string {
  return (
    date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }) + " UTC"
  );
}

// ─── Tool call display ─────────────────────────────────────────
const TOOL_LABELS: Record<string, string> = {
  get_surface_weather:           "Surface Weather",
  get_winds_aloft:               "Winds Aloft",
  check_notam_airspace:          "NOTAM Check",
  astra_list_balloons:           "Balloon Catalog",
  astra_list_parachutes:         "Parachute Catalog",
  astra_calculate_nozzle_lift:   "Nozzle Lift",
  astra_calculate_balloon_volume:"Balloon Volume",
  astra_run_simulation:          "Monte Carlo Simulation",
};

function getArgSummary(name: string, args: Record<string, unknown>): string {
  switch (name) {
    case "get_surface_weather":
    case "get_winds_aloft":
    case "check_notam_airspace":
      return `${args.latitude}°, ${args.longitude}°`;
    case "astra_calculate_nozzle_lift":
    case "astra_calculate_balloon_volume":
      return `${args.balloon_model} · ${args.gas_type}`;
    case "astra_run_simulation":
      return `${args.balloon_model} · ${args.num_runs ?? 5} runs`;
    default:
      return "";
  }
}

function ToolCallsSection({ toolCalls }: { toolCalls: ToolCallRecord[] }) {
  if (!toolCalls.length) return null;
  return (
    <details className={styles.toolCalls}>
      <summary className={styles.toolCallsSummary}>
        <span className={styles.toolCallsChevron}>▸</span>
        <span className={styles.toolCallsLabel}>
          {toolCalls.length} tool{toolCalls.length !== 1 ? "s" : ""} used
        </span>
      </summary>
      <ul className={styles.toolCallsList}>
        {toolCalls.map((tc, i) => {
          const summary = getArgSummary(tc.name, tc.args);
          return (
            <li key={i} className={styles.toolCallItem}>
              <span className={styles.toolCallDot} />
              <span className={styles.toolCallName}>
                {TOOL_LABELS[tc.name] ?? tc.name}
              </span>
              {summary && (
                <span className={styles.toolCallArgs}>{summary}</span>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

// ─── Message components ────────────────────────────────────────
function AssistantMessage({ message }: { message: Message }) {
  return (
    <div className={styles.assistantCard}>
      <div className={styles.assistantHeader}>
        <span className={styles.assistantLabel}>STRATOS AI</span>
        <span className={styles.assistantTime}>{formatUtcTime(message.createdAt)}</span>
      </div>
      <div className={styles.assistantText}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ node: _node, ...props }) => (
              <a {...props} target="_blank" rel="noreferrer" />
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
      {message.trajectoryArtifact && (
        <TrajectoryArtifactMap artifact={message.trajectoryArtifact} />
      )}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <ToolCallsSection toolCalls={message.toolCalls} />
      )}
    </div>
  );
}

function UserMessage({ message }: { message: Message }) {
  return (
    <div className={styles.userRow}>
      <div className={styles.userBubble}>
        <p className={styles.userText}>{message.content}</p>
      </div>
    </div>
  );
}

// ─── Loading indicator ─────────────────────────────────────────
const LOADING_STEPS = [
  "Analyzing request…",
  "Querying weather data…",
  "Running simulation…",
  "Computing trajectory…",
];

function TypingIndicator() {
  const [stepIdx, setStepIdx] = useState(0);

  useEffect(() => {
    const id = setInterval(
      () => setStepIdx((i) => (i + 1) % LOADING_STEPS.length),
      2800,
    );
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className={styles.loadingShell}
      aria-live="polite"
      aria-label={`STRATOS AI ${LOADING_STEPS[stepIdx]}`}
    >
      <div className={styles.loadingHeader}>
        <span className={styles.assistantLabel}>STRATOS AI</span>
        <span className={styles.loadingMicrodot} aria-hidden="true" />
        <span className={styles.loadingMeta}>processing</span>
      </div>
      <div className={styles.loadingState}>
        <span key={stepIdx} className={styles.loadingStep}>
          {LOADING_STEPS[stepIdx]}
        </span>
      </div>
    </div>
  );
}

// ─── Empty state ───────────────────────────────────────────────
function EmptyState() {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyInner}>
        <div className={styles.emptyLogoWrap}>
          <Image
            src="/assets/STRATOS_LOGO_SVG/Color.svg"
            alt="STRATOS"
            width={52}
            height={52}
            priority
          />
        </div>
        <p className={styles.emptyLabel}>STRATOS Mission Chat</p>
        <p className={styles.emptySubtitle}>
          Ask anything about telemetry, trajectory, or flight data.
        </p>
      </div>
    </div>
  );
}

// ─── Main ──────────────────────────────────────────────────────
interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
}

export default function MessageList({
  messages,
  isLoading = false,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className={styles.container}>
      {messages.length === 0 && !isLoading ? (
        <EmptyState />
      ) : (
        <div className={styles.feed}>
          {messages.map((msg) =>
            msg.role === "user"
              ? <UserMessage key={msg.id} message={msg} />
              : <AssistantMessage key={msg.id} message={msg} />
          )}
          {isLoading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
