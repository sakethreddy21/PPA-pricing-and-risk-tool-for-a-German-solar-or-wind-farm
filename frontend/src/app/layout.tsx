import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "German Renewable PPA Pricing & Risk Terminal",
  description: "Institutional Pay-as-Produced PPA valuation, cannibalization haircut modeling, and quantitative Monte Carlo risk simulation for German Solar and Wind farms.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/favicon.ico" />
      </head>
      <body>{children}</body>
    </html>
  );
}
