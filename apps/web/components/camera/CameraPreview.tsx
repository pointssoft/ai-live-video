"use client";

import { useEffect, useRef } from "react";

export function CameraPreview({ stream }: { stream: MediaStream }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    video.srcObject = stream;
    void video.play();
    return () => { video.srcObject = null; };
  }, [stream]);
  return <div className="camera-frame"><video ref={ref} muted playsInline aria-label="Live camera preview" /><div className="framing-guide" aria-hidden="true" /></div>;
}
