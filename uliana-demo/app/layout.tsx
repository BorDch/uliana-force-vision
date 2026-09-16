import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ULIANA — Recorded movement review",
  description: "A Skoltech Team 10 prototype for reviewing recorded movement and illustrative hand-zone signals.",
  icons: {
    icon: `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/favicon.svg`,
    shortcut: `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/favicon.svg`,
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
