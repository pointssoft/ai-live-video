import { apiRequest } from "./api-client";
import type { Generation, GenerationPage, GenerationProgressStage, GenerationStatus } from "@/types/api";

function idempotencyHeaders(idempotencyKey: string): HeadersInit {
  return { "Idempotency-Key": idempotencyKey };
}

export function createIdempotencyKey(action = "generation"): string {
  return `${action}-${crypto.randomUUID()}`;
}

export const createGeneration = (portraitId: string, motionAssetId: string, idempotencyKey: string) =>
  apiRequest<Generation>("/api/v1/generations", {
    method: "POST",
    headers: idempotencyHeaders(idempotencyKey),
    body: JSON.stringify({ portrait_id: portraitId, motion_asset_id: motionAssetId }),
  });

export const getGeneration = (id: string) =>
  apiRequest<Generation>(`/api/v1/generations/${encodeURIComponent(id)}`);

export const listGenerations = (cursor?: string, limit = 20) =>
  apiRequest<GenerationPage>(`/api/v1/generations?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);

export const cancelGeneration = (id: string) =>
  apiRequest<void>(`/api/v1/generations/${encodeURIComponent(id)}/cancel`, { method: "POST" });

export const retryGeneration = (id: string, idempotencyKey: string) =>
  apiRequest<Generation>(`/api/v1/generations/${encodeURIComponent(id)}/retry`, {
    method: "POST",
    headers: idempotencyHeaders(idempotencyKey),
  });

export const deleteGeneration = (id: string) =>
  apiRequest<void>(`/api/v1/generations/${encodeURIComponent(id)}`, { method: "DELETE" });

export const TERMINAL_GENERATION_STATUSES: ReadonlySet<GenerationStatus> = new Set([
  "SUCCEEDED",
  "FAILED",
  "TIMED_OUT",
  "CANCELED",
]);

const STAGE_LABELS: Record<string, string> = {
  WAITING_FOR_GPU: "Waiting for GPU",
  GENERATING: "Generating video",
  VALIDATING_INPUT: "Validating inputs",
  DOWNLOADING: "Preparing inputs",
  VALIDATING_MEDIA: "Validating media",
  RUNNING_INFERENCE: "Generating video",
  UPLOADING_OUTPUT: "Saving result",
  VERIFYING_OUTPUT: "Finalizing result",
  COMPLETED: "Completed",
  FAILED: "Generation failed",
  TIMED_OUT: "Generation timed out",
  CANCELED: "Canceled",
};

export function generationStageLabel(stage: GenerationProgressStage, status: GenerationStatus): string {
  if (stage && STAGE_LABELS[stage]) return STAGE_LABELS[stage];
  if (status === "CREATED" || status === "QUEUED") return "Waiting to start";
  if (status === "CANCEL_REQUESTED") return "Cancellation requested";
  if (status === "RUNNING") return "Processing";
  return STAGE_LABELS[status] ?? status.toLowerCase().replaceAll("_", " ");
}
