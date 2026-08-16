"use client";

import { useCallback, useEffect, useState } from "react";

export function useCamera() {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [error, setError] = useState("");

  const stop = useCallback(() => {
    setStream((current) => { current?.getTracks().forEach((track) => track.stop()); return null; });
  }, []);

  const open = useCallback(async (deviceId?: string) => {
    if (!navigator.mediaDevices?.getUserMedia) { setError("Camera recording is not supported in this browser."); return; }
    stop(); setError("");
    try {
      const next = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: "user" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      next.getVideoTracks()[0]?.addEventListener("ended", () => { setError("The camera stream was interrupted."); setStream(null); }, { once: true });
      setStream(next);
      setDevices((await navigator.mediaDevices.enumerateDevices()).filter((item) => item.kind === "videoinput"));
    } catch (caught) {
      const name = caught instanceof DOMException ? caught.name : "";
      setError(name === "NotAllowedError" ? "Camera permission was denied. Enable it in browser site settings." : name === "NotFoundError" ? "No camera was found." : "The camera is unavailable or being used by another application.");
    }
  }, [stop]);

  useEffect(() => stop, [stop]);
  return { stream, devices, error, open, stop };
}
