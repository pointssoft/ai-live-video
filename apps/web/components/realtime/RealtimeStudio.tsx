"use client";

import { useEffect, useRef, useState } from "react";
import {
  createLocalVideoTrack,
  LocalVideoTrack,
  Room,
  RoomEvent,
  Track,
  type RemoteTrack,
} from "livekit-client";
import { listPortraits } from "@/lib/portraits";
import { createRealtimeSession } from "@/lib/realtime-sessions";
import type { Portrait } from "@/types/api";

export function RealtimeStudio() {
  const [portraits, setPortraits] = useState<Portrait[]>([]);
  const [portraitId, setPortraitId] = useState("");
  const [status, setStatus] = useState("Select a portrait to begin.");
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  const roomRef = useRef<Room | null>(null);
  const cameraTrackRef = useRef<LocalVideoTrack | null>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const outputVideoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    listPortraits()
      .then((page) => {
        setPortraits(page.items);
        setPortraitId(page.items[0]?.id ?? "");
      })
      .catch(() => setError("Could not load portraits."));
  }, []);

  const stop = async () => {
    cameraTrackRef.current?.stop();
    cameraTrackRef.current = null;
    await roomRef.current?.disconnect();
    roomRef.current = null;
    if (localVideoRef.current) localVideoRef.current.srcObject = null;
    if (outputVideoRef.current) outputVideoRef.current.srcObject = null;
    setConnecting(false);
    setStatus("Session ended.");
  };

  useEffect(() => () => { void stop(); }, []);

  const start = async () => {
    if (!portraitId || connecting || roomRef.current) return;
    setConnecting(true);
    setError("");
    setStatus("Connecting…");

    try {
      const session = await createRealtimeSession(portraitId);
      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Video && outputVideoRef.current) {
          track.attach(outputVideoRef.current);
          setStatus("Live");
        }
      });
      room.on(RoomEvent.Disconnected, () => setStatus("Disconnected."));

      await room.connect(session.server_url, session.participant_token);
      const cameraTrack = await createLocalVideoTrack({
        resolution: { width: 1280, height: 720, frameRate: 30 },
        facingMode: "user",
      });
      cameraTrackRef.current = cameraTrack;
      if (localVideoRef.current) cameraTrack.attach(localVideoRef.current);
      await room.localParticipant.publishTrack(cameraTrack, { source: Track.Source.Camera });
      setStatus("Camera connected. Waiting for the worker…");
    } catch (caught) {
      await stop();
      setError(caught instanceof Error ? caught.message : "Could not start the live session.");
    } finally {
      setConnecting(false);
    }
  };

  return (
    <section className="realtime-page">
      <div>
        <p className="eyebrow">Realtime portrait</p>
        <h1>Live animation</h1>
        <p>Camera video is processed by the realtime worker and returned over WebRTC.</p>
      </div>

      <div className="panel realtime-controls">
        <label htmlFor="portrait">Portrait</label>
        <select id="portrait" value={portraitId} onChange={(event) => setPortraitId(event.target.value)} disabled={Boolean(roomRef.current)}>
          {portraits.map((portrait) => <option key={portrait.id} value={portrait.id}>{portrait.id.slice(0, 8)}</option>)}
        </select>
        <div className="actions detail-actions">
          <button type="button" onClick={start} disabled={!portraitId || connecting || Boolean(roomRef.current)}>Start</button>
          <button type="button" className="secondary" onClick={() => void stop()} disabled={!roomRef.current}>Stop</button>
        </div>
        <p role="status">{status}</p>
        {error && <p className="error" role="alert">{error}</p>}
        {!portraits.length && <p><a href="/portraits">Upload a portrait first.</a></p>}
      </div>

      <div className="realtime-videos">
        <figure><video ref={localVideoRef} autoPlay muted playsInline /><figcaption>Camera</figcaption></figure>
        <figure><video ref={outputVideoRef} autoPlay playsInline /><figcaption>Processed output</figcaption></figure>
      </div>
    </section>
  );
}
