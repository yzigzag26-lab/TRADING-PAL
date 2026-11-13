import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Trading Pal — Trading Intelligence",
  description: "A focused workspace for evidence-led cryptocurrency market analysis.",
  applicationName: "Trading Pal",
};

export const viewport: Viewport = { themeColor: "#090D14", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={inter.variable}>{children}</body></html>;
}