import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";
import ThemeToggle from "../components/theme-toggle";
import "./globals.css";
import "./brand-theme.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Baymax — Trading Intelligence",
  description: "A focused workspace for evidence-led cryptocurrency market analysis.",
  applicationName: "Baymax",
};

export const viewport: Viewport = { themeColor: "#0a0d11", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.variable}>
        {children}
        <ThemeToggle />
      </body>
    </html>
  );
}
