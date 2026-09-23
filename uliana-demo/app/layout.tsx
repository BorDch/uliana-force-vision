import type { Metadata, Viewport } from "next";
import { Instrument_Serif } from "next/font/google";

import { MotionRoot } from "@/components/motion-root";
import { EntryRouter } from "@/components/entry-router";
import "./globals.css";

const display = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  display: "swap",
  variable: "--font-display",
  fallback: ["Georgia", "Times New Roman", "serif"],
});

// GitHub Pages serves this site as a project site, so the base path is part of
// every absolute asset URL. The build sets NEXT_PUBLIC_BASE_PATH.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const origin = "https://bordch.github.io";
const siteBase = `${origin}${basePath}`;

const title = "ULIANA — Train alone. Don’t review alone.";
const description =
  "Turn one phone recording into a clear push-up review with complete repetition counts, supported camera observations, exact moments to review and comparable session history.";
const shareImage = {
  url: `${siteBase}/og-image.png`,
  width: 1200,
  height: 630,
  alt: "ULIANA: clear repetition-by-repetition review for independent exercise.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#8f4a38",
};

export const metadata: Metadata = {
  metadataBase: new URL(`${siteBase}/`),
  title,
  description,
  applicationName: "ULIANA",
  authors: [{ name: "Boris Cherkassov" }],
  keywords: ["push-up analysis", "pose estimation", "recorded session review", "Skoltech", "prototype"],
  // Absolute URLs: the base path is already part of the GitHub Pages project URL.
  alternates: { canonical: `${siteBase}/` },
  icons: {
    icon: `${basePath}/favicon.svg`,
    shortcut: `${basePath}/favicon.svg`,
    apple: `${basePath}/apple-touch-icon.png`,
  },
  manifest: `${basePath}/manifest.webmanifest`,
  openGraph: {
    type: "website",
    siteName: "ULIANA",
    url: `${siteBase}/`,
    title,
    description,
    images: [shareImage],
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: [shareImage.url],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={display.variable}>
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        <EntryRouter>{children}</EntryRouter>
        <MotionRoot />
      </body>
    </html>
  );
}
