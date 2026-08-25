"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createLocalVideoTrack,
  LocalVideoTrack,
  Room,
  RoomEvent,
  Track,
  type RemoteTrack,
} from "livekit-client";
import { listPortraits } from "@/lib/portraits";
import { createRealtimeSession, terminateRealtimeSession } from "@/lib/realtime-sessions";
import type { Portrait } from "@/types/api";

interface StoredSession {
  sessionId: string;
  podId: string | null;
  roomName: string;
  serverUrl: string;
  participantToken: string;
  portraitId: string;
  expiresAt: number;
}

const SESSION_STORAGE_KEY = "mimicmotion_realtime_session";
const WORKER_WAIT_TIMEOUT_MS = 150_000;

function getStoredSession(): StoredSession | null {
  try {
    const stored = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!stored) return null;
    const session: StoredSession = JSON.parse(stored);
    // Check if session has expired
    if (Date.now() > session.expiresAt) {
      localStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

function storeSession(session: StoredSession): void {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch (e) {
    console.error("Failed to store session:", e);
  }
}

function clearStoredSession(): void {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch (e) {
    console.error("Failed to clear stored session:", e);
  }
}

export function RealtimeStudio() {
  const [portraits, setPortraits] = useState<Portrait[]>([]);
  const [portraitId, setPortraitId] = useState("");
  const [status, setStatus] = useState("Select a portrait to begin.");
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [changingPortrait, setChangingPortrait] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const roomRef = useRef<Room | null>(null);
  const cameraTrackRef = useRef<LocalVideoTrack | null>(null);
  const outputTrackRef = useRef<RemoteTrack | null>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const outputVideoRef = useRef<HTMLVideoElement>(null);
  const sessionInfoRef = useRef<{ sessionId: string; podId: string | null } | null>(null);
  const currentPortraitIdRef = useRef<string>("");
  const workerWaitTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isLive = status === "Live";

  useEffect(() => {
    const cameraTrack = cameraTrackRef.current;
    const localVideo = localVideoRef.current;
    if (cameraTrack && localVideo) cameraTrack.attach(localVideo);

    const outputTrack = outputTrackRef.current;
    const outputVideo = outputVideoRef.current;
    if (outputTrack && outputVideo) outputTrack.attach(outputVideo);
  }, [isLive]);

  useEffect(() => {
    listPortraits()
      .then((page) => {
        setPortraits(page.items);
        setPortraitId(page.items[0]?.id ?? "");
      })
      .catch(() => setError("Could not load portraits."));
  }, []);

  const stop = useCallback(async () => {
    if (workerWaitTimeoutRef.current) {
      clearTimeout(workerWaitTimeoutRef.current);
      workerWaitTimeoutRef.current = null;
    }

    const sessionInfo = sessionInfoRef.current;
    sessionInfoRef.current = null;

    cameraTrackRef.current?.stop();
    cameraTrackRef.current = null;
    outputTrackRef.current = null;
    await roomRef.current?.disconnect();
    roomRef.current = null;
    if (localVideoRef.current) localVideoRef.current.srcObject = null;
    if (outputVideoRef.current) outputVideoRef.current.srcObject = null;

    clearStoredSession();
    setConnecting(false);
    setReconnecting(false);
    setStatus("Session ended.");

    if (sessionInfo?.podId) {
      try {
        await terminateRealtimeSession(sessionInfo.sessionId, sessionInfo.podId);
      } catch (caught) {
        console.error("Failed to terminate realtime pod:", caught);
      }
    }
  }, []);

  const waitForWorker = useCallback((room: Room) => {
    if (workerWaitTimeoutRef.current) clearTimeout(workerWaitTimeoutRef.current);
    if (outputTrackRef.current) return;

    workerWaitTimeoutRef.current = setTimeout(() => {
      workerWaitTimeoutRef.current = null;
      if (roomRef.current !== room || outputTrackRef.current) return;

      setError("The realtime worker did not become ready. Please try again.");
      void stop();
    }, WORKER_WAIT_TIMEOUT_MS);
  }, [stop]);

  useEffect(() => () => { void stop(); }, [stop]);

  const reconnectToSession = useCallback(async (stored: StoredSession) => {
    setStatus("Reconnecting to previous session…");
    setError("");

    try {
      sessionInfoRef.current = { sessionId: stored.sessionId, podId: stored.podId };
      currentPortraitIdRef.current = stored.portraitId;

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Video) {
          outputTrackRef.current = track;
          if (outputVideoRef.current) track.attach(outputVideoRef.current);
          if (workerWaitTimeoutRef.current) {
            clearTimeout(workerWaitTimeoutRef.current);
            workerWaitTimeoutRef.current = null;
          }
          setStatus("Live");
          setReconnecting(false);
        }
      });
      room.on(RoomEvent.Disconnected, () => {
        if (workerWaitTimeoutRef.current) {
          clearTimeout(workerWaitTimeoutRef.current);
          workerWaitTimeoutRef.current = null;
        }
        clearStoredSession();
        setStatus("Disconnected.");
      });

      await room.connect(stored.serverUrl, stored.participantToken);
      const cameraTrack = await createLocalVideoTrack({
        resolution: { width: 1280, height: 720, frameRate: 30 },
        facingMode: "user",
      });
      cameraTrackRef.current = cameraTrack;
      if (localVideoRef.current) cameraTrack.attach(localVideoRef.current);
      await room.localParticipant.publishTrack(cameraTrack, { source: Track.Source.Camera });
      setStatus("Reconnected. Waiting for the worker…");
      waitForWorker(room);
    } catch (caught) {
      await stop();
      throw caught;
    }
  }, [stop, waitForWorker]);

  // Check for an existing session on mount.
  useEffect(() => {
    const stored = getStoredSession();
    if (!stored) return;

    setReconnecting(true);
    setPortraitId(stored.portraitId);
    void reconnectToSession(stored).catch((caught) => {
      console.error("Failed to reconnect:", caught);
      clearStoredSession();
      setReconnecting(false);
      setError("Previous session expired or could not be restored.");
    });
  }, [reconnectToSession]);

  const changePortrait = async (newPortraitId: string) => {
    if (!roomRef.current || changingPortrait) return;

    setChangingPortrait(true);
    setStatus("Changing portrait…");
    setError("");

    try {
      // Get the new portrait URL from the portraits list
      const portrait = portraits.find(p => p.id === newPortraitId);
      if (!portrait) {
        throw new Error("Portrait not found");
      }

      // Send portrait change message via data channel
      const encoder = new TextEncoder();
      const message = JSON.stringify({
        type: "change_portrait",
        portrait_id: newPortraitId,
        portrait_url: portrait.image_url,
      });

      await roomRef.current.localParticipant.publishData(
        encoder.encode(message),
        { reliable: true }
      );

      currentPortraitIdRef.current = newPortraitId;
      setPortraitId(newPortraitId);
      setStatus("Portrait changed successfully");

      // Reset status to "Live" after 2 seconds
      setTimeout(() => {
        if (roomRef.current) setStatus("Live");
      }, 2000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to change portrait.");
      setStatus("Live");
    } finally {
      setChangingPortrait(false);
    }
  };

  const start = async () => {
    if (!portraitId || connecting || roomRef.current) return;
    setConnecting(true);
    setError("");
    setStatus("Connecting…");

    try {
      const session = await createRealtimeSession(portraitId);
      sessionInfoRef.current = { sessionId: session.session_id, podId: session.pod_id ?? null };
      currentPortraitIdRef.current = portraitId;

      // Store session for reconnection
      const expiresAt = Date.now() + (session.expires_in_seconds * 1000);
      storeSession({
        sessionId: session.session_id,
        podId: session.pod_id ?? null,
        roomName: session.room_name,
        serverUrl: session.server_url,
        participantToken: session.participant_token,
        portraitId: portraitId,
        expiresAt: expiresAt,
      });

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Video) {
          outputTrackRef.current = track;
          if (outputVideoRef.current) track.attach(outputVideoRef.current);
          if (workerWaitTimeoutRef.current) {
            clearTimeout(workerWaitTimeoutRef.current);
            workerWaitTimeoutRef.current = null;
          }
          setStatus("Live");
        }
      });
      room.on(RoomEvent.Disconnected, () => {
        if (workerWaitTimeoutRef.current) {
          clearTimeout(workerWaitTimeoutRef.current);
          workerWaitTimeoutRef.current = null;
        }
        clearStoredSession();
        setStatus("Disconnected.");
      });

      await room.connect(session.server_url, session.participant_token);
      const cameraTrack = await createLocalVideoTrack({
        resolution: { width: 1280, height: 720, frameRate: 30 },
        facingMode: "user",
      });
      cameraTrackRef.current = cameraTrack;
      if (localVideoRef.current) cameraTrack.attach(localVideoRef.current);
      await room.localParticipant.publishTrack(cameraTrack, { source: Track.Source.Camera });
      setStatus("Camera connected. Waiting for the worker…");
      waitForWorker(room);
    } catch (caught) {
      await stop();
      setError(caught instanceof Error ? caught.message : "Could not start the live session.");
    } finally {
      setConnecting(false);
    }
  };

  if (isLive || reconnecting) {
    return (
      <div className="fullscreen-live-layout">
        <div className="live-output-container">
          <video ref={outputVideoRef} autoPlay playsInline className="main-live-video" />
          {reconnecting && (
            <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', background: 'rgba(0,0,0,0.7)', padding: '20px', borderRadius: '8px', color: 'white' }}>
              Reconnecting to session...
            </div>
          )}
        </div>
        <div className="live-sidebar">
          <div className="live-sidebar-header">
            <h3>Live Settings</h3>
          </div>
          <div className="live-control-group">
            <label htmlFor="portrait-live">Portrait</label>
            <select
              id="portrait-live"
              value={portraitId}
              onChange={(event) => void changePortrait(event.target.value)}
              disabled={!roomRef.current || changingPortrait || reconnecting}
            >
              {portraits.map((portrait) => <option key={portrait.id} value={portrait.id}>{portrait.id.slice(0, 8)}</option>)}
            </select>
          </div>
          <div className="live-control-group">
            <button type="button" className="secondary stop-button" onClick={() => void stop()} disabled={!roomRef.current || reconnecting}>Stop Session</button>
          </div>
          <div className="camera-preview-container">
            <p className="preview-label">Camera</p>
            <video ref={localVideoRef} autoPlay muted playsInline className="preview-video" />
          </div>
        </div>
      </div>
    );
  }

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
