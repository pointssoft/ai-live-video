import { describe, expect, it, vi } from "vitest";

vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");

describe("API client errors", () => {
  it("preserves the stable API error message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: "AUTH_REQUIRED", message: "Authentication is required.", request_id: "req-1", details: null },
    }), { status: 401, headers: { "content-type": "application/json" } })));
    const { apiRequest } = await import("@/lib/api-client");
    await expect(apiRequest("/api/v1/me")).rejects.toMatchObject({ code: "AUTH_REQUIRED", requestId: "req-1" });
  });
});
