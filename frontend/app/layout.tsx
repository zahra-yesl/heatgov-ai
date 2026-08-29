import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  // If the font cannot be fetched at build time, the browser falls back to a
  // system sans-serif rather than blocking the render.
  fallback: ["system-ui", "Segoe UI", "Arial", "sans-serif"],
});

export const metadata: Metadata = {
  title: "HeatGov AI - Central Los Angeles",
  description:
    "Turns hyperlocal FortyGuard temperature data into a budgeted heat-mitigation plan.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="h-full overflow-x-auto bg-slate-100 text-slate-900">
        {children}
      </body>
    </html>
  );
}
