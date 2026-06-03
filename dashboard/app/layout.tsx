import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";

export const metadata: Metadata = {
  title: "GoldMind AI — XAUUSD Trading Terminal",
  description:
    "Institutional-grade multi-agent AI trading dashboard for XAUUSD (Gold).",
};

export const viewport: Viewport = {
  themeColor: "#0a0e14",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-terminal-bg text-terminal-text">
        <div className="flex h-screen overflow-hidden">
          {/* Sidebar is hidden on small screens; nav still reachable via routes. */}
          <div className="hidden md:block">
            <Sidebar />
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <Topbar />
            <main className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
              <div className="mx-auto max-w-[1400px]">{children}</div>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
