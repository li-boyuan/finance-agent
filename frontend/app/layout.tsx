import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Finance Agent",
  description: "AI personal finance advisor — plain-language guidance on budgeting, debt, investing, and major decisions.",
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
