"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiClientError } from "@/lib/errors";
import {
  cancelGeneration,
  createIdempotencyKey,
  deleteGeneration,
  generationStageLabel,
  getGeneration,
  retryGeneration,
  TERMINAL_GENERATION_STATUSES,
} from "@/lib/generations";
import type { Generation } from "@/types/api";

function elapsedLabel(createdAt: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export default function GenerationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [generation, setGeneration] = useState<Generation | null>(null);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const [, setClock] = useState(0);
  const generationStatus = generation?.status;

  const load = useCallback(async () => {
    try {
      const current = await getGeneration(id);
      setGeneration(current);
      setError("");
      setConnectionError(false);
      return current;
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.status === 401) {
        router.replace(`/login?next=/generations/${encodeURIComponent(id)}`);
        return null;
      }
      setConnectionError(true);
      setError(caught instanceof Error ? caught.message : "Could not refresh generation status.");
      return null;
    }
  }, [id, router]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!generationStatus || TERMINAL_GENERATION_STATUSES.has(generationStatus)) return;
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const schedule = () => {
      const delay = document.visibilityState === "visible" ? 5000 : 20000;
      timer = setTimeout(async () => {
        if (stopped) return;
        await load();
        schedule();
      }, delay);
    };
    const visible = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", visible);
    schedule();
    return () => { stopped = true; clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [generationStatus, load]);

  useEffect(() => {
    if (!generation || TERMINAL_GENERATION_STATUSES.has(generation.status)) return;
    const timer = setInterval(() => setClock((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [generation]);

  async function cancel() {
    if (!generation || !window.confirm("Request cancellation for this generation?")) return;
    setActionPending(true);
    setError("");
    try {
      await cancelGeneration(generation.id);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Cancellation could not be requested.");
    } finally {
      setActionPending(false);
    }
  }

  async function retry() {
    if (!generation || actionPending) return;
    setActionPending(true);
    setError("");
    try {
      const updated = await retryGeneration(generation.id, createIdempotencyKey("retry"));
      setGeneration(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "This generation cannot be retried.");
    } finally {
      setActionPending(false);
    }
  }

  async function remove() {
    if (!generation || !window.confirm("Delete this generation and schedule its output for removal?")) return;
    setActionPending(true);
    setError("");
    try {
      await deleteGeneration(generation.id);
      router.push("/generations");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Generation could not be deleted.");
      setActionPending(false);
    }
  }

  if (!generation) return <section className="dashboard" aria-busy="true"><h1>Generation</h1>{error ? <p className="error">{error}</p> : <p>Loading status…</p>}{connectionError && <button onClick={() => void load()}>Try again</button>}</section>;

  const terminal = TERMINAL_GENERATION_STATUSES.has(generation.status);
  const failed = generation.status === "FAILED" || generation.status === "TIMED_OUT";
  const processing = !terminal;

  return (
    <section className="generation-detail">
      <p className="eyebrow">Generation {generation.id.slice(0, 8)}</p>
      <h1>{generation.status === "SUCCEEDED" ? "Your video is ready" : generationStageLabel(generation.execution.progress_stage, generation.status)}</h1>
      {error && <p role="alert" className="error panel">{error}</p>}
      {connectionError && <button className="secondary" onClick={() => void load()}>Retry connection</button>}

      {processing && <div className="panel" aria-live="polite"><h2>{generationStageLabel(generation.execution.progress_stage, generation.status)}</h2><p>Elapsed: {elapsedLabel(generation.created_at)}</p><p>You can leave this page. Processing continues in the background.</p>{generation.status !== "CANCEL_REQUESTED" && <button className="secondary" disabled={actionPending} onClick={() => void cancel()}>Cancel generation</button>}</div>}

      {generation.status === "SUCCEEDED" && generation.output && <div className="result"><video key={generation.output.download_url} src={generation.output.download_url} controls playsInline preload="metadata" /><div className="actions"><a className="button" href={generation.output.download_url} download>Download MP4</a><button className="secondary" onClick={() => void load()}>Refresh media link</button></div></div>}

      {failed && <div className="panel"><h2>Generation did not complete</h2><p>{generation.execution.failure_message ?? "The generation failed. You may try it again."}</p><p className="hint">Reference: {generation.id}</p><button disabled={actionPending} onClick={() => void retry()}>Retry generation</button></div>}
      {generation.status === "CANCELED" && <div className="panel"><h2>Generation canceled</h2><p>No output was created.</p></div>}

      <div className="actions detail-actions"><Link className="button secondary" href="/generations">Generation history</Link><Link className="button" href="/create">Create another</Link>{terminal && <button className="danger-button" disabled={actionPending} onClick={() => void remove()}>Delete</button>}</div>
    </section>
  );
}
