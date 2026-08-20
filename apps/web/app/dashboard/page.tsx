"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { currentUser } from "@/lib/auth";
import { ApiClientError } from "@/lib/errors";
import { generationStageLabel, listGenerations } from "@/lib/generations";
import type { Generation, User } from "@/types/api";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [recent, setRecent] = useState<Generation[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([currentUser(), listGenerations()])
      .then(([account, page]) => { setUser(account); setRecent(page.items.slice(0, 5)); })
      .catch((caught: unknown) => {
        if (caught instanceof ApiClientError && caught.status === 401) {
          router.replace("/login");
          return;
        }
        setError(caught instanceof Error ? caught.message : "Could not load the account.");
      });
  }, [router]);

  if (error) return <section className="dashboard"><h1>Dashboard</h1><p className="error">{error}</p></section>;
  if (!user) return <section className="dashboard" aria-busy="true"><h1>Dashboard</h1><p>Loading account…</p></section>;

  return (
    <section className="dashboard">
      <div className="dashboard-header"><div><p className="eyebrow">Account ready</p><h1>Dashboard</h1></div><LogoutButton /></div>
      <div className="panel"><h2>{user.email}</h2><p>Status: {user.status}</p></div>
      <div className="panel"><h2>Create a motion video</h2><p>Upload a portrait and record a validated 5–15 second camera clip.</p><div className="actions"><Link className="button" href="/create">Start capture</Link><Link className="button secondary" href="/portraits">Portrait library</Link></div></div>
      <div className="panel"><div className="dashboard-header"><h2>Recent generations</h2><Link href="/generations">View all</Link></div>{recent.length === 0 ? <p>No generations yet.</p> : <div className="generation-list compact">{recent.map((item) => <Link className="generation-card" href={`/generations/${item.id}`} key={item.id}><div><strong>{item.status === "SUCCEEDED" ? "Completed" : generationStageLabel(item.execution.progress_stage, item.status)}</strong><span>{new Date(item.created_at).toLocaleString()}</span></div><span className={`status status-${item.status.toLowerCase()}`}>{item.status}</span></Link>)}</div>}</div>
    </section>
  );
}
