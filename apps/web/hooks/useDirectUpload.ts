"use client";

import { useRef, useState } from "react";
import { completeUpload, createUpload, putDirect, waitForUpload } from "@/lib/uploads";
import type { Upload, UploadContentType, UploadKind } from "@/types/api";

export function useDirectUpload() {
  const controller = useRef<AbortController | null>(null);
  const [phase, setPhase] = useState("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  async function upload(blob: Blob, kind: UploadKind, contentType: UploadContentType): Promise<Upload> {
    controller.current?.abort(); controller.current = new AbortController(); setError("");
    try {
      setPhase("preparing"); const session = await createUpload(blob, kind, contentType);
      setPhase("uploading"); await putDirect(session, blob, (loaded, total) => setProgress(Math.round(loaded / total * 100)), controller.current.signal);
      setPhase("validating"); await completeUpload(session.upload_id);
      const result = await waitForUpload(session.upload_id, controller.current.signal);
      setPhase("ready"); return result;
    } catch (caught) { setPhase("failed"); setError(caught instanceof Error ? caught.message : "Upload failed."); throw caught; }
  }
  return { phase, progress, error, upload, cancel: () => controller.current?.abort() };
}
