"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { selectRecordingFormat, type RecordingFormat } from "@/lib/media-capabilities";

export interface Recording { blob: Blob; url: string; durationMs: number; format: RecordingFormat }

export function useMediaRecorder(stream: MediaStream | null) {
  const recorder = useRef<MediaRecorder | null>(null);
  const timers = useRef<number[]>([]);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [error, setError] = useState("");

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const retake = useCallback(() => { if (recording) URL.revokeObjectURL(recording.url); setRecording(null); setError(""); }, [recording]);
  const stop = useCallback(() => { if (recorder.current?.state === "recording") recorder.current.stop(); }, []);
  const cancelCountdown = useCallback(() => { clearTimers(); setCountdown(null); }, []);

  const begin = useCallback(() => {
    const format = selectRecordingFormat();
    if (!stream || !format) { setError("No supported camera recording format is available."); return; }
    const chunks: BlobPart[] = [];
    const mediaRecorder = new MediaRecorder(stream, { mimeType: format.recorderMimeType });
    recorder.current = mediaRecorder;
    mediaRecorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    const started = performance.now();
    mediaRecorder.onstop = () => {
      const durationMs = performance.now() - started;
      const blob = new Blob(chunks, { type: format.uploadContentType });
      setRecording({ blob, url: URL.createObjectURL(blob), durationMs, format });
      setStartedAt(null);
    };
    setStartedAt(started); mediaRecorder.start(250);
    timers.current.push(window.setTimeout(() => mediaRecorder.state === "recording" && mediaRecorder.stop(), 14_800));
  }, [stream]);

  const startCountdown = useCallback(() => {
    clearTimers(); setCountdown(3);
    [1, 2].forEach((second) => timers.current.push(window.setTimeout(() => setCountdown(3 - second), second * 1000)));
    timers.current.push(window.setTimeout(() => { setCountdown(null); begin(); }, 3000));
  }, [begin]);

  useEffect(() => () => { clearTimers(); if (recorder.current?.state === "recording") recorder.current.stop(); }, []);
  return { countdown, recording, isRecording: startedAt !== null, error, startCountdown, cancelCountdown, stop, retake };
}
