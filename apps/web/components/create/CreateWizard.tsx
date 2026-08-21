/* eslint-disable @next/next/no-img-element -- signed private URLs are dynamic and short-lived */
"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CameraPreview } from "@/components/camera/CameraPreview";
import { useCamera } from "@/hooks/useCamera";
import { useDirectUpload } from "@/hooks/useDirectUpload";
import { useMediaRecorder } from "@/hooks/useMediaRecorder";
import { currentUser } from "@/lib/auth";
import { ApiClientError } from "@/lib/errors";
import { createGeneration, createIdempotencyKey } from "@/lib/generations";
import { createPortrait, listPortraits } from "@/lib/portraits";
import type { Portrait, Upload, UploadContentType } from "@/types/api";

export function CreateWizard() {
  const router = useRouter();
  const [step, setStep] = useState<"portrait" | "camera" | "review" | "ready">("portrait");
  const [portraits, setPortraits] = useState<Portrait[]>([]);
  const [portrait, setPortrait] = useState<Portrait | null>(null);
  const [motion, setMotion] = useState<Upload | null>(null);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submissionKey = useRef<string | null>(null);
  const camera = useCamera();
  const portraitAspectRatio = portrait?.original_asset.width && portrait.original_asset.height
    ? portrait.original_asset.width / portrait.original_asset.height
    : 3 / 4;
  const recorder = useMediaRecorder(camera.stream, portraitAspectRatio);
  const transfer = useDirectUpload();
  const portraitTransfer = useDirectUpload();

  useEffect(() => {
    currentUser()
      .then(() => listPortraits())
      .then((page) => setPortraits(page.items))
      .catch((caught: unknown) => {
        if (caught instanceof ApiClientError && caught.status === 401) {
          router.replace("/login?next=/create");
          return;
        }
        setMessage(caught instanceof Error ? caught.message : "Could not load portraits.");
      });
  }, [router]);

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
    if (!allowed.includes(file.type) || file.size > 15 * 1024 * 1024) {
      setMessage("Choose a JPEG, PNG, or WebP portrait under 15 MB.");
      return;
    }
    setMessage("Uploading and validating portrait…");
    try {
      const asset = await portraitTransfer.upload(file, "PORTRAIT_ORIGINAL", file.type as UploadContentType);
      const created = await createPortrait(asset.id);
      setPortrait(created);
      setPortraits((items) => [created, ...items]);
      setMessage("");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Portrait upload failed.");
    }
  }

  async function uploadMotion() {
    if (!recorder.recording || !portrait) return;
    setMessage("Uploading and validating motion clip…");
    try {
      const uploaded = await transfer.upload(
        recorder.recording.blob,
        "MOTION_INPUT",
        recorder.recording.format.uploadContentType,
      );
      setMotion(uploaded);
      camera.stop();
      setMessage(`Inputs ready. Motion validated as ${uploaded.video_codec ?? "video"}.`);
      setStep("ready");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Motion upload failed.");
    }
  }

  async function submitGeneration() {
    if (!portrait || !motion || submitting) return;
    setSubmitting(true);
    setMessage("Submitting generation…");
    submissionKey.current ??= createIdempotencyKey();
    try {
      const generation = await createGeneration(portrait.id, motion.id, submissionKey.current);
      router.push(`/generations/${generation.id}`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Could not start generation.");
      setSubmitting(false);
    }
  }

  const durationValid = !!recorder.recording
    && recorder.recording.durationMs >= 5000
    && recorder.recording.durationMs <= 15000;

  return (
    <section className="wizard">
      <ol className="stepper" aria-label="Creation steps">
        <li aria-current={step === "portrait" ? "step" : undefined}>1 Portrait</li>
        <li aria-current={step === "camera" ? "step" : undefined}>2 Camera</li>
        <li aria-current={step === "review" ? "step" : undefined}>3 Review</li>
        <li aria-current={step === "ready" ? "step" : undefined}>4 Generate</li>
      </ol>
      {message && <p role="status" aria-live="polite" className={transfer.phase === "failed" ? "error" : "panel"}>{message}</p>}

      {step === "portrait" && (
        <div>
          <h1>Select a portrait</h1>
          <p>Use one clearly visible person in good lighting.</p>
          <label className="button file-button">Upload portrait<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => event.target.files?.[0] && void uploadPortrait(event.target.files[0])} /></label>
          <div className="portrait-grid">{portraits.map((item) => <button className={`portrait-card ${portrait?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => setPortrait(item)}><img src={item.image_url} alt="Uploaded portrait" /><span>{item.original_asset.width && item.original_asset.height ? `${item.original_asset.width}×${item.original_asset.height}` : "Portrait"}</span></button>)}</div>
          <button disabled={!portrait} onClick={() => setStep("camera")}>Continue to camera</button>
        </div>
      )}

      {step === "camera" && (
        <div>
          <h1>Record motion</h1>
          {!camera.stream ? <><p>Camera access begins only after you click Allow camera. No audio is recorded.</p><button onClick={() => void camera.open()}>Allow camera</button></> : <><div className="camera-layout"><CameraPreview stream={camera.stream} aspectRatio={portraitAspectRatio ?? 3 / 4} /><aside className="panel"><p>The preview and recorded video use the selected portrait&apos;s aspect ratio. Keep one person fully visible and move at a moderate speed.</p>{camera.devices.length > 1 && <label>Camera<select onChange={(event) => void camera.open(event.target.value)}>{camera.devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}</select></label>}</aside></div>{recorder.countdown !== null && <p className="countdown" aria-live="polite">Recording in {recorder.countdown}</p>}{recorder.isRecording ? <button className="recording" onClick={recorder.stop}>Stop recording</button> : <button onClick={recorder.startCountdown}>Start 3-second countdown</button>}{recorder.countdown !== null && <button className="secondary" onClick={recorder.cancelCountdown}>Cancel countdown</button>}</>}
          {(camera.error || recorder.error) && <p role="alert" className="error">{camera.error || recorder.error}</p>}
        </div>
      )}

      {step === "review" && recorder.recording && portrait && (
        <div>
          <h1>Review inputs</h1>
          <div className="review-grid"><img src={portrait.image_url} alt="Selected portrait" /><video src={recorder.recording.url} controls playsInline /></div>
          <p>Duration: {(recorder.recording.durationMs / 1000).toFixed(1)} seconds · Upload size: {(recorder.recording.blob.size / 1024 / 1024).toFixed(1)} MB</p>
          {!durationValid && <p role="alert" className="error">Recording must be between 5 and 15 seconds.</p>}
          <div className="actions"><button className="secondary" onClick={() => { recorder.retake(); setStep("camera"); }}>Retake</button><button disabled={!durationValid || transfer.phase === "uploading"} onClick={() => void uploadMotion()}>Upload motion</button></div>
          {transfer.phase === "uploading" && <progress value={transfer.progress} max="100">{transfer.progress}%</progress>}
        </div>
      )}

      {step === "ready" && portrait && motion && (
        <div>
          <h1>Ready to generate</h1>
          <div className="panel"><p>Your inputs passed validation. Generation uses cloud GPU processing and may take several minutes. Source files are stored privately according to the service retention policy. Source audio is not included in the generated video.</p></div>
          <div className="actions"><button className="secondary" disabled={submitting} onClick={() => setStep("portrait")}>Change inputs</button><button disabled={submitting} onClick={() => void submitGeneration()}>{submitting ? "Starting…" : "Generate video"}</button></div>
        </div>
      )}
    </section>
  );
}
