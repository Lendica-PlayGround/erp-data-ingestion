import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Phase 2 Exploration Agent",
  description: "ChatGPT-style agent for exploring unfamiliar datasets and APIs.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full">{children}</body>
    </html>
  );
}
