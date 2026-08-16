/* eslint-disable @next/next/no-img-element -- signed private URLs are dynamic and short-lived */
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { currentUser } from "@/lib/auth";
import { deletePortrait, listPortraits } from "@/lib/portraits";
import type { Portrait } from "@/types/api";

export default function PortraitsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Portrait[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { currentUser().then(() => listPortraits()).then((page) => setItems(page.items)).catch(() => router.replace("/login?next=/portraits")); }, [router]);
  return <section className="wizard"><h1>Portrait library</h1><p>Deleting a portrait currently also deletes its original uploaded image.</p>{error && <p role="alert" className="error">{error}</p>}<div className="portrait-grid">{items.map((portrait) => <article className="portrait-card" key={portrait.id}><img src={portrait.image_url} alt="Uploaded portrait" /><span>{portrait.original_asset.width}×{portrait.original_asset.height}</span><button className="secondary" onClick={async () => { if (!confirm("Delete this portrait and its original image?")) return; try { await deletePortrait(portrait.id); setItems((all) => all.filter((item) => item.id !== portrait.id)); } catch (caught) { setError(caught instanceof Error ? caught.message : "Delete failed."); } }}>Delete</button></article>)}</div>{items.length === 0 && <p className="panel">No portraits yet. Upload one from the Create flow.</p>}<a className="button" href="/create">Create inputs</a></section>;
}
