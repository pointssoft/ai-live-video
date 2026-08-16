/* eslint-disable @next/next/no-img-element -- signed private URLs are dynamic and short-lived */
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CameraPreview } from "@/components/camera/CameraPreview";
import { useCamera } from "@/hooks/useCamera";
import { useDirectUpload } from "@/hooks/useDirectUpload";
import { useMediaRecorder } from "@/hooks/useMediaRecorder";
import { currentUser } from "@/lib/auth";
import { createPortrait, listPortraits } from "@/lib/portraits";
import type { Portrait, UploadContentType } from "@/types/api";

export function CreateWizard() {
  const router = useRouter();
  const [step, setStep] = useState<"portrait" | "camera" | "review" | "ready">("portrait");
  const [portraits, setPortraits] = useState<Portrait[]>([]);
  const [portrait, setPortrait] = useState<Portrait | null>(null);
  const [message, setMessage] = useState("");
  const camera = useCamera();
  const recorder = useMediaRecorder(camera.stream);
  const transfer = useDirectUpload();
  const portraitTransfer = useDirectUpload();

  useEffect(() => { currentUser().then(() => listPortraits()).then((page) => setPortraits(page.items)).catch(() => router.replace("/login?next=/create")); }, [router]);

  useEffect(() => {
    if (recorder.recording && step === "camera") setStep("review");
  }, [recorder.recording, step]);

  useEffect(() => {
    if (!recorder.isRecording && transfer.phase !== "uploading") return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [recorder.isRecording, transfer.phase]);

  async function uploadPortrait(file: File) {
    const allowed = ["image/jpeg", "image/png", "image/webp"];
    if (!allowed.includes(file.type) || file.size > 15 * 1024 * 1024) { setMessage("Choose a JPEG, PNG, or WebP portrait under 15 MB."); return; }
    setMessage("Uploading and validating portrait…");
    try {
      const asset = await portraitTransfer.upload(file, "PORTRAIT_ORIGINAL", file.type as UploadContentType);
      const created = await createPortrait(asset.id); setPortrait(created); setPortraits((items) => [created, ...items]); setMessage("");
    } catch (caught) { setMessage(caught instanceof Error ? caught.message : "Portrait upload failed."); }
  }

  async function uploadMotion() {
    if (!recorder.recording || !portrait) return;
    setMessage("Uploading and validating motion clip…");
    try {
      const motion = await transfer.upload(recorder.recording.blob, "MOTION_INPUT", recorder.recording.format.uploadContentType);
      camera.stop(); setMessage(`Inputs ready. Motion validated as ${motion.video_codec ?? "video"}. Generation will be added next.`); setStep("ready");
    } catch (caught) { setMessage(caught instanceof Error ? caught.message : "Motion upload failed."); }
  }

  const durationValid = !!recorder.recording && recorder.recording.durationMs >= 5000 && recorder.recording.durationMs <= 15000;
  return <section className="wizard">
    <ol className="stepper" aria-label="Creation steps"><li aria-current={step === "portrait" ? "step" : undefined}>1 Portrait</li><li aria-current={step === "camera" ? "step" : undefined}>2 Camera</li><li aria-current={step === "review" ? "step" : undefined}>3 Review</li><li aria-current={step === "ready" ? "step" : undefined}>4 Ready</li></ol>
    {message && <p role="status" aria-live="polite" className={transfer.phase === "failed" ? "error" : "panel"}>{message}</p>}
    {step === "portrait" && <div><h1>Select a portrait</h1><p>Use one clearly visible person in good lighting.</p><label className="button file-button">Upload portrait<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => e.target.files?.[0] && void uploadPortrait(e.target.files[0])} /></label><div className="portrait-grid">{portraits.map((item) => <button className={`portrait-card ${portrait?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => setPortrait(item)}><img src={item.image_url} alt="Uploaded portrait" /><span>{item.original_asset.width}×{item.original_asset.height}</span></button>)}</div><button disabled={!portrait} onClick={() => setStep("camera")}>Continue to camera</button></div>}
    {step === "camera" && <div><h1>Record motion</h1>{!camera.stream ? <><p>Camera access begins only after you click Allow camera. No audio is recorded.</p><button onClick={() => void camera.open()}>Allow camera</button></> : <><div className="camera-layout"><CameraPreview stream={camera.stream} /><aside className="panel"><p>Keep one person fully visible and move at a moderate speed.</p>{camera.devices.length > 1 && <label>Camera<select onChange={(e) => void camera.open(e.target.value)}>{camera.devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}</select></label>}</aside></div>{recorder.countdown !== null && <p className="countdown" aria-live="polite">Recording in {recorder.countdown}</p>}{recorder.isRecording ? <button className="recording" onClick={recorder.stop}>Stop recording</button> : <button onClick={recorder.startCountdown}>Start 3-second countdown</button>}{recorder.countdown !== null && <button className="secondary" onClick={recorder.cancelCountdown}>Cancel countdown</button>}</>}{(camera.error || recorder.error) && <p role="alert" className="error">{camera.error || recorder.error}</p>}</div>}
    {step === "review" && recorder.recording && portrait && <div><h1>Review inputs</h1><div className="review-grid"><img src={portrait.image_url} alt="Selected portrait" /><video src={recorder.recording.url} controls playsInline /></div><p>Duration: {(recorder.recording.durationMs / 1000).toFixed(1)} seconds</p>{!durationValid && <p role="alert" className="error">Recording must be between 5 and 15 seconds.</p>}<div className="actions"><button className="secondary" onClick={() => { recorder.retake(); setStep("camera"); }}>Retake</button><button disabled={!durationValid || transfer.phase === "uploading"} onClick={() => void uploadMotion()}>Upload motion</button></div>{transfer.phase === "uploading" && <progress value={transfer.progress} max="100">{transfer.progress}%</progress>}</div>}
    {step === "ready" && <div><h1>Inputs ready</h1><p>Your portrait and motion clip passed validation. GPU generation is not enabled yet.</p><a className="button" href="/dashboard">Back to dashboard</a></div>}
  </section>;
}
