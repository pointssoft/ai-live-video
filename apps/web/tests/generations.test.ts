import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Generation } from "@/types/api";

vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");

const generation: Generation = {
  id: "generation-1",
  portrait_id: "portrait-1",
  motion_asset_id: "motion-1",
  status: "CREATED",
  execution: { state: "CREATED", attempt_id: null, provider_status: null, progress_stage: null, failure_code: null, failure_message: null },
  output: null,
  created_at: "2026-08-18T00:00:00Z",
  updated_at: "2026-08-18T00:00:00Z",
  started_at: null,
  completed_at: null,
  failed_at: null,
  timed_out_at: null,
  canceled_at: null,
};

describe("generation client", () => {
  beforeEach(() => vi.resetModules());

  it("sends generation inputs and an idempotency key", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "csrf-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(generation), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    const { createGeneration } = await import("@/lib/generations");
    await createGeneration("portrait-1", "motion-1", "generation-key-1");

    const [, request] = fetchMock.mock.calls[1];
    expect(request.method).toBe("POST");
    expect(new Headers(request.headers).get("Idempotency-Key")).toBe("generation-key-1");
    expect(JSON.parse(request.body)).toEqual({
      portrait_id: "portrait-1",
      motion_asset_id: "motion-1",
      profile: "mimicmotion-v1.1-quality-v1",
      seed: 42,
    });
  });

  it("maps known and fallback progress stages", async () => {
    const { generationStageLabel } = await import("@/lib/generations");
    expect(generationStageLabel("RUNNING_INFERENCE", "RUNNING")).toBe("Generating video");
    expect(generationStageLabel(null, "CANCEL_REQUESTED")).toBe("Cancellation requested");
    expect(generationStageLabel("UNKNOWN_STAGE", "RUNNING")).toBe("Processing");
  });
});
