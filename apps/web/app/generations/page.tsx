"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiClientError } from "@/lib/errors";
import { generationStageLabel, listGenerations } from "@/lib/generations";
import type { Generation } from "@/types/api";

function statusLabel(item: Generation): string {
  return item.status === "SUCCEEDED" ? "Completed" : generationStageLabel(item.execution.progress_stage, item.status);
}

export default function GenerationsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Generation[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listGenerations()
      .then((page) => { setItems(page.items); setCursor(page.next_cursor); })
      .catch((caught: unknown) => {
        if (caught instanceof ApiClientError && caught.status === 401) {
          router.replace("/login?next=/generations");
          return;
        }
        setError(caught instanceof Error ? caught.message : "Could not load generations.");
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function loadMore() {
    if (!cursor) return;
    setLoading(true);
    try {
      const page = await listGenerations(cursor);
      setItems((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load more generations.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="dashboard">
      <div className="dashboard-header"><div><p className="eyebrow">Private results</p><h1>Generation history</h1></div><Link className="button" href="/create">Create video</Link></div>
      {error && <p role="alert" className="error panel">{error}</p>}
      {loading && items.length === 0 && <p>Loading generations…</p>}
      {!loading && !error && items.length === 0 && <div className="panel"><h2>No generations yet</h2><p>Create a portrait and record a short motion clip to get started.</p><Link className="button" href="/create">Start creating</Link></div>}
      <div className="generation-list">{items.map((item) => <Link className="generation-card" href={`/generations/${item.id}`} key={item.id}><div><strong>{statusLabel(item)}</strong><span>{new Date(item.created_at).toLocaleString()}</span></div><span className={`status status-${item.status.toLowerCase()}`}>{item.status}</span></Link>)}</div>
      {cursor && <button className="secondary" disabled={loading} onClick={() => void loadMore()}>{loading ? "Loading…" : "Load more"}</button>}
    </section>
  );
}
