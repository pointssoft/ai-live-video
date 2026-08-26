import { apiRequest } from "./api-client";
import type { Portrait, PortraitPage } from "@/types/api";

export const listPortraits = (cursor?: string) => apiRequest<PortraitPage>(`/api/v1/portraits?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
export const getPortrait = (id: string) => apiRequest<Portrait>(`/api/v1/portraits/${encodeURIComponent(id)}`);
export const createPortrait = (originalAssetId: string) => apiRequest<Portrait>("/api/v1/portraits", { method: "POST", body: JSON.stringify({ original_asset_id: originalAssetId }) });
export const deletePortrait = (id: string) => apiRequest<void>(`/api/v1/portraits/${id}`, { method: "DELETE" });
