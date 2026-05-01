import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradeLog",
  description: "Trade journal and analytics for active traders",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
