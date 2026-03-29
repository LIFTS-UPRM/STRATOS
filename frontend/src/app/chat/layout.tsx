import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chat · STRATOS",
};

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
