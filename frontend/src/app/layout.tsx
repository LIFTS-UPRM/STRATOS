import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "STRATOS",
  description:
    "System for Trajectory, Analysis & Telemetry Operations in the Stratosphere",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
