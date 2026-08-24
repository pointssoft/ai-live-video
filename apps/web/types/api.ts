export interface ApiErrorBody {
  error?: { code: string; message: string; request_id: string | null; details: unknown };
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
}

export interface User { id: string; email: string; status: string; created_at: string }
export interface AuthResponse { user: User }

export type UploadKind = "PORTRAIT_ORIGINAL" | "MOTION_INPUT";
export type UploadContentType = "image/jpeg" | "image/png" | "image/webp" | "video/webm" | "video/mp4";
export type MediaState = "UPLOADING" | "UPLOADED" | "VALIDATING" | "READY" | "VALIDATION_FAILED" | "UPLOAD_EXPIRED" | "UPLOAD_FAILED" | "DELETED";

export interface UploadSession {
  upload_id: string; state: MediaState; object_key: string; method: "PUT";
  upload_url: string; expires_at: string; required_headers: Record<string, string>;
}
export interface Upload {
  id: string; kind: UploadKind; state: MediaState; content_type: string;
  detected_content_type: string | null; size_bytes: number; sha256: string;
  width: number | null; height: number | null; duration_ms: number | null;
  fps: number | null; frame_count: number | null; video_codec: string | null;
  created_at: string; uploaded_at: string | null; validated_at: string | null; ready_at: string | null;
  validation_error_code: string | null; validation_error_detail: string | null;
}
export interface Portrait {
  id: string; status: "READY";
  original_asset: { id: string; content_type: string; size_bytes: number; sha256: string; width: number | null; height: number | null };
  image_url: string; image_url_expires_at: string; thumbnail_url: string | null;
  thumbnail_url_expires_at: string | null; created_at: string; updated_at: string;
}
export interface PortraitPage { items: Portrait[]; next_cursor: string | null }

export interface RealtimeSession {
  session_id: string;
  room_name: string;
  server_url: string;
  participant_token: string;
  expires_in_seconds: number;
  pod_id?: string | null;
}

export type GenerationStatus = "CREATED" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "TIMED_OUT" | "CANCEL_REQUESTED" | "CANCELED";
export type GenerationProgressStage = string | null;
export interface GenerationExecution {
  state: GenerationStatus;
  attempt_id: string | null;
  provider_status: string | null;
  progress_stage: GenerationProgressStage;
  failure_code: string | null;
  failure_message: string | null;
}
export interface GenerationOutput {
  content_type: string;
  size_bytes: number;
  sha256: string;
  download_url: string;
  download_url_expires_at: string;
}
export interface Generation {
  id: string;
  portrait_id: string;
  motion_asset_id: string;
  status: GenerationStatus;
  execution: GenerationExecution;
  output: GenerationOutput | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  timed_out_at: string | null;
  canceled_at: string | null;
}
export interface GenerationPage { items: Generation[]; next_cursor: string | null }
