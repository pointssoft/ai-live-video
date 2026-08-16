import { apiRequest } from "./api-client";
import { sha256 } from "./sha256";
import type { Upload, UploadContentType, UploadKind, UploadSession } from "@/types/api";

export async function createUpload(blob: Blob, kind: UploadKind, contentType: UploadContentType): Promise<UploadSession> {
  return apiRequest<UploadSession>("/api/v1/uploads", {
    method: "POST",
    body: JSON.stringify({ kind, content_type: contentType, size_bytes: blob.size, sha256: await sha256(blob) }),
  });
}

export function putDirect(
  session: UploadSession,
  blob: Blob,
  onProgress: (loaded: number, total: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(session.method, session.upload_url);
    Object.entries(session.required_headers).forEach(([name, value]) => xhr.setRequestHeader(name, value));
    xhr.upload.onprogress = (event) => onProgress(event.loaded, event.total || blob.size);
    xhr.onerror = () => reject(new Error("The storage upload failed."));
    xhr.onabort = () => reject(new DOMException("Upload aborted", "AbortError"));
    xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error("The storage upload was rejected."));
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(blob);
  });
}

export async function completeUpload(id: string): Promise<Upload> {
  return apiRequest<Upload>(`/api/v1/uploads/${id}/complete`, { method: "POST" });
}
export async function getUpload(id: string): Promise<Upload> {
  return apiRequest<Upload>(`/api/v1/uploads/${id}`);
}
export async function waitForUpload(id: string, signal?: AbortSignal): Promise<Upload> {
  for (;;) {
    if (signal?.aborted) throw new DOMException("Polling aborted", "AbortError");
    const upload = await getUpload(id);
    if (upload.state === "READY") return upload;
    if (["VALIDATION_FAILED", "UPLOAD_EXPIRED", "UPLOAD_FAILED", "DELETED"].includes(upload.state)) {
      throw new Error(upload.validation_error_detail ?? "Media validation failed.");
    }
    await new Promise((resolve) => setTimeout(resolve, document.hidden ? 5000 : 1500));
  }
}
