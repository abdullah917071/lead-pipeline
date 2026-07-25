import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lead Pipeline | Control Center",
  description: "Autonomous lead-to-account conversion funnel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">{children}</body>
    </html>
  );
}
