import Link from "next/link";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "MimicMotion", description: "MimicMotion platform" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><header className="site-header"><Link href="/" className="brand">MimicMotion</Link><nav aria-label="Main navigation"><Link href="/dashboard">Dashboard</Link><Link href="/create">Create</Link><Link href="/generations">History</Link><Link href="/portraits">Portraits</Link><Link href="/login">Login</Link></nav></header><main>{children}</main></body></html>;
}
