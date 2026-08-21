"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { selectRecordingFormat, type RecordingFormat } from "@/lib/media-capabilities";

export interface Recording { blob: Blob; url: string; durationMs: number; format: RecordingFormat }

interface Crop {
  sourceX: number;
  sourceY: number;
  sourceWidth: number;
  sourceHeight: number;
  outputWidth: number;
  outputHeight: number;
}

export function recordingCrop(sourceWidth: number, sourceHeight: number, targetRatio: number): Crop {
  const sourceRatio = sourceWidth / sourceHeight;
  const outputWidth = sourceRatio > targetRatio
    ? Math.floor(sourceHeight * targetRatio / 2) * 2
    : Math.floor(sourceWidth / 2) * 2;
  const outputHeight = sourceRatio > targetRatio
    ? Math.floor(sourceHeight / 2) * 2
    : Math.floor(sourceWidth / targetRatio / 2) * 2;
  return {
    sourceX: (sourceWidth - outputWidth) / 2,
    sourceY: (sourceHeight - outputHeight) / 2,
    sourceWidth: outputWidth,
    sourceHeight: outputHeight,
    outputWidth,
    outputHeight,
  };
}

export function useMediaRecorder(stream: MediaStream | null, targetRatio: number | null) {
  const recorder = useRef<MediaRecorder | null>(null);
  const timers = useRef<number[]>([]);
  const recordingCleanup = useRef<(() => void) | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [error, setError] = useState("");

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const retake = useCallback(() => { if (recording) URL.revokeObjectURL(recording.url); setRecording(null); setError(""); }, [recording]);
  const stop = useCallback(() => { if (recorder.current?.state === "recording") recorder.current.stop(); }, []);
  const cancelCountdown = useCallback(() => { clearTimers(); setCountdown(null); }, []);

  const begin = useCallback(async () => {
    const format = selectRecordingFormat();
    if (!stream || !format || !targetRatio || !Number.isFinite(targetRatio)) {
      setError("No supported camera recording format is available.");
      return;
    }

    try {
      const source = document.createElement("video");
      source.muted = true;
      source.playsInline = true;
      source.srcObject = stream;
      await source.play();
      const settings = stream.getVideoTracks()[0]?.getSettings();
      const sourceWidth = source.videoWidth || settings?.width || 1280;
      const sourceHeight = source.videoHeight || settings?.height || 720;
      const crop = recordingCrop(sourceWidth, sourceHeight, targetRatio);
      const canvas = document.createElement("canvas");
      canvas.width = crop.outputWidth;
      canvas.height = crop.outputHeight;
      const context = canvas.getContext("2d");
      if (!context || typeof canvas.captureStream !== "function") throw new Error("Canvas recording is unavailable.");

      let frame = 0;
      const draw = () => {
        context.drawImage(
          source,
          crop.sourceX,
          crop.sourceY,
          crop.sourceWidth,
          crop.sourceHeight,
          0,
          0,
          crop.outputWidth,
          crop.outputHeight,
        );
        frame = requestAnimationFrame(draw);
      };
      draw();
      const croppedStream = canvas.captureStream(settings?.frameRate || 30);
      const chunks: BlobPart[] = [];
      const mediaRecorder = new MediaRecorder(croppedStream, { mimeType: format.recorderMimeType });
      recorder.current = mediaRecorder;
      recordingCleanup.current = () => {
        cancelAnimationFrame(frame);
        croppedStream.getTracks().forEach((track) => track.stop());
        source.pause();
        source.srcObject = null;
      };
      mediaRecorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      const started = performance.now();
      mediaRecorder.onstop = () => {
        recordingCleanup.current?.();
        recordingCleanup.current = null;
        const durationMs = performance.now() - started;
        const blob = new Blob(chunks, { type: format.uploadContentType });
        setRecording({ blob, url: URL.createObjectURL(blob), durationMs, format });
        setStartedAt(null);
      };
      setStartedAt(started);
      mediaRecorder.start(250);
      timers.current.push(window.setTimeout(() => mediaRecorder.state === "recording" && mediaRecorder.stop(), 14_800));
    } catch {
      recordingCleanup.current?.();
      recordingCleanup.current = null;
      setStartedAt(null);
      setError("Could not start a portrait-matched camera recording.");
    }
  }, [stream, targetRatio]);

  const startCountdown = useCallback(() => {
    clearTimers(); setCountdown(3);
    [1, 2].forEach((second) => timers.current.push(window.setTimeout(() => setCountdown(3 - second), second * 1000)));
    timers.current.push(window.setTimeout(() => { setCountdown(null); void begin(); }, 3000));
  }, [begin]);

  useEffect(() => () => {
    clearTimers();
    if (recorder.current?.state === "recording") recorder.current.stop();
    recordingCleanup.current?.();
  }, []);
  return { countdown, recording, isRecording: startedAt !== null, error, startCountdown, cancelCountdown, stop, retake };
}
