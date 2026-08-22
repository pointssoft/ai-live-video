import { apiRequest } from "./api-client";
import type { RealtimeSession } from "@/types/api";

export const createRealtimeSession = (portraitId: string) =>
  apiRequest<RealtimeSession>("/api/v1/realtime-sessions", {
    method: "POST",
    body: JSON.stringify({ portrait_id: portraitId }),
  });
