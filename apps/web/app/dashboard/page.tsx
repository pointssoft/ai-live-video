"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { currentUser } from "@/lib/auth";
import { ApiClientError } from "@/lib/errors";
import type { User } from "@/types/api";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    currentUser()
      .then(setUser)
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
      <div className="panel"><h2>Create motion inputs</h2><p>Upload a portrait and record a validated 5–15 second camera clip.</p><div className="actions"><a className="button" href="/create">Start capture</a><a className="button secondary" href="/portraits">Portrait library</a></div></div>
    </section>
  );
}
