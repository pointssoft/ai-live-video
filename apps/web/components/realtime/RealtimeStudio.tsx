"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  createLocalVideoTrack,
  LocalVideoTrack,
  Room,
  RoomEvent,
  Track,
  type RemoteTrack,
  type RemoteVideoTrack,
} from "livekit-client";
import { getPortrait, listPortraits } from "@/lib/portraits";
import { createRealtimeSession, terminateRealtimeSession } from "@/lib/realtime-sessions";
import {
  BROADCAST_HEIGHT,
  BROADCAST_WIDTH,
  MAX_BROADCAST_ZOOM,
  MIN_BROADCAST_ZOOM,
  getMediaMtxEndpoints,
  VideoWhipPublisher,
  type BroadcastRotation,
  type BroadcastStatus,
  type BroadcastViewport,
  type MediaMtxEndpoints,
} from "@/lib/video-whip-publisher";
import type { Portrait } from "@/types/api";

interface ExpressionControls {
  eyeOpenness: number;
  mouthOpenness: number;
}

interface StoredSession {
  sessionId: string;
  podId: string | null;
  roomName: string;
  serverUrl: string;
  participantToken: string;
  portraitId: string;
  expiresAt: number;
  eyeOpenness?: number;
  mouthOpenness?: number;
}

interface ViewerCredentials {
  wsUrl: string;
  roomId: string;
  accessToken: string;
  expiresInSeconds: number;
}

interface ViewerCredentialsPanelProps {
  credentials: ViewerCredentials;
  copied: boolean;
  onCopy: () => void;
}

function serializeViewerCredentials(credentials: ViewerCredentials, formatted = false): string {
  return JSON.stringify({
    wsUrl: credentials.wsUrl,
    accessToken: credentials.accessToken,
    roomId: credentials.roomId,
  }, null, formatted ? 2 : undefined);
}

function ViewerCredentialsPanel({ credentials, copied, onCopy }: ViewerCredentialsPanelProps) {
  const qrValue = serializeViewerCredentials(credentials);

  return (
    <div className="viewer-credentials">
      <h4>Read-only app credentials</h4>
      <label htmlFor="viewer-ws-url">WebSocket URL</label>
      <input id="viewer-ws-url" readOnly value={credentials.wsUrl} />
      <label htmlFor="viewer-room-id">Room ID</label>
      <input id="viewer-room-id" readOnly value={credentials.roomId} />
      <label htmlFor="viewer-access-token">Access token</label>
      <textarea id="viewer-access-token" readOnly rows={3} value={credentials.accessToken} />
      <button type="button" className="secondary" onClick={onCopy}>
        {copied ? "Copied" : "Copy app credentials"}
      </button>
      <div className="viewer-credentials-qr">
        <QRCodeSVG
          value={qrValue}
          size={256}
          level="L"
          marginSize={4}
          bgColor="#ffffff"
          fgColor="#080d19"
          title="Read-only app credentials QR code"
        />
        <span>Scan with your mobile app</span>
      </div>
      <p className="viewer-credentials-hint">
        Read-only token. It expires in {Math.ceil(credentials.expiresInSeconds / 60)} minutes.
      </p>
    </div>
  );
}

interface BroadcastControlsProps {
  endpoints: MediaMtxEndpoints | null;
  status: BroadcastStatus;
  rotation: BroadcastRotation;
  viewport: BroadcastViewport;
  error: string;
  copied: boolean;
  canStart: boolean;
  hasPublisher: boolean;
  onStart: () => void;
  onStop: () => void;
  onCopy: () => void;
  onRotationChange: (rotation: BroadcastRotation) => void;
  onZoomChange: (zoom: number) => void;
  onPanChange: (panX: number, panY: number) => void;
  onViewportReset: () => void;
}

function BroadcastControls({
  endpoints,
  status,
  rotation,
  viewport,
  error,
  copied,
  canStart,
  hasPublisher,
  onStart,
  onStop,
  onCopy,
  onRotationChange,
  onZoomChange,
  onPanChange,
  onViewportReset,
}: BroadcastControlsProps) {
  const statusLabel = endpoints
    ? status.charAt(0).toUpperCase() + status.slice(1)
    : "Not configured";

  return (
    <section className="broadcast-controls" aria-labelledby="broadcast-controls-title">
      <div className="broadcast-heading">
        <h4 id="broadcast-controls-title">LAN RTSP Broadcast</h4>
        <span className="broadcast-status" data-status={endpoints ? status : "unconfigured"}>
          <span className="broadcast-status-dot" aria-hidden="true" />
          {statusLabel}
        </span>
      </div>

      {endpoints ? (
        <>
          <label htmlFor="broadcast-rtsp-url">RTSP URL</label>
          <textarea
            id="broadcast-rtsp-url"
            className="broadcast-url"
            readOnly
            rows={2}
            value={endpoints.rtspUrl}
          />
          <div className="broadcast-actions">
            {hasPublisher ? (
              <button
                type="button"
                className="secondary"
                onClick={onStop}
                disabled={status === "stopping"}
              >
                {status === "stopping" ? "Stopping…" : "Stop Broadcast"}
              </button>
            ) : (
              <button type="button" onClick={onStart} disabled={!canStart}>
                {status === "connecting" ? "Connecting…" : "Start Broadcast"}
              </button>
            )}
            <button type="button" className="secondary" onClick={onCopy}>
              {copied ? "Copied" : "Copy RTSP URL"}
            </button>
          </div>
          <div className="broadcast-rotation">
            <label htmlFor="broadcast-rotation">Rotation</label>
            <select
              id="broadcast-rotation"
              value={rotation}
              onChange={(event) =>
                onRotationChange(Number(event.target.value) as BroadcastRotation)
              }
            >
              <option value={0}>0°</option>
              <option value={90}>90°</option>
              <option value={180}>180°</option>
              <option value={270}>270°</option>
            </select>
          </div>
          <div className="broadcast-viewport">
            <div className="broadcast-viewport-heading">
              <label htmlFor="broadcast-zoom">Zoom and position</label>
              <button
                type="button"
                className="broadcast-viewport-reset"
                onClick={onViewportReset}
                disabled={
                  viewport.zoom === MIN_BROADCAST_ZOOM &&
                  viewport.panX === 0 &&
                  viewport.panY === 0
                }
              >
                Reset
              </button>
            </div>
            <div className="broadcast-zoom-control">
              <input
                id="broadcast-zoom"
                type="range"
                min={MIN_BROADCAST_ZOOM}
                max={MAX_BROADCAST_ZOOM}
                step="0.1"
                value={viewport.zoom}
                onChange={(event) => onZoomChange(Number(event.target.value))}
              />
              <output htmlFor="broadcast-zoom">{viewport.zoom.toFixed(1)}×</output>
            </div>
            <div className="broadcast-pan-controls" aria-label="Move zoomed broadcast frame">
              <button
                type="button"
                className="secondary broadcast-pan-up"
                aria-label="Move frame up"
                onClick={() => onPanChange(viewport.panX, viewport.panY - 0.1)}
                disabled={viewport.zoom === MIN_BROADCAST_ZOOM}
              >
                ↑
              </button>
              <button
                type="button"
                className="secondary broadcast-pan-left"
                aria-label="Move frame left"
                onClick={() => onPanChange(viewport.panX - 0.1, viewport.panY)}
                disabled={viewport.zoom === MIN_BROADCAST_ZOOM}
              >
                ←
              </button>
              <button
                type="button"
                className="secondary broadcast-pan-center"
                aria-label="Center frame"
                onClick={() => onPanChange(0, 0)}
                disabled={
                  viewport.zoom === MIN_BROADCAST_ZOOM ||
                  (viewport.panX === 0 && viewport.panY === 0)
                }
              >
                •
              </button>
              <button
                type="button"
                className="secondary broadcast-pan-right"
                aria-label="Move frame right"
                onClick={() => onPanChange(viewport.panX + 0.1, viewport.panY)}
                disabled={viewport.zoom === MIN_BROADCAST_ZOOM}
              >
                →
              </button>
              <button
                type="button"
                className="secondary broadcast-pan-down"
                aria-label="Move frame down"
                onClick={() => onPanChange(viewport.panX, viewport.panY + 0.1)}
                disabled={viewport.zoom === MIN_BROADCAST_ZOOM}
              >
                ↓
              </button>
            </div>
            <p className="broadcast-viewport-hint">
              Zoom in, then use the arrows to move the live broadcast frame.
            </p>
          </div>
          <a href={endpoints.whepUrl} target="_blank" rel="noreferrer">
            Open WHEP diagnostic viewer
          </a>
          <p className="broadcast-hint">
            Anonymous video-only output for devices on this trusted LAN. LiveKit viewer
            credentials are not used.
          </p>
        </>
      ) : (
        <p className="broadcast-hint">
          Set NEXT_PUBLIC_MEDIAMTX_HOST to enable LAN broadcasting.
        </p>
      )}

      {error && <p className="broadcast-error" role="alert">{error}</p>}
    </section>
  );
}


const SESSION_STORAGE_KEY = "mimicmotion_realtime_session";
const MEDIA_MTX_ENDPOINTS = getMediaMtxEndpoints(
  process.env.NEXT_PUBLIC_MEDIAMTX_HOST,
);
const WORKER_WAIT_TIMEOUT_MS = 300_000;
const EXPRESSION_CONTROLS_DEBOUNCE_MS = 120;
const DEFAULT_BROADCAST_VIEWPORT: BroadcastViewport = {
  zoom: MIN_BROADCAST_ZOOM,
  panX: 0,
  panY: 0,
};
const DEFAULT_EXPRESSION_CONTROLS: ExpressionControls = {
  eyeOpenness: -0.10,
  mouthOpenness: -0.15,
};

function clampExpressionControl(value: unknown, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.min(1, Math.max(-1, value));
}

function expressionControlsFromSession(session: StoredSession): ExpressionControls {
  return {
    eyeOpenness: clampExpressionControl(
      session.eyeOpenness,
      DEFAULT_EXPRESSION_CONTROLS.eyeOpenness,
    ),
    mouthOpenness: clampExpressionControl(
      session.mouthOpenness,
      DEFAULT_EXPRESSION_CONTROLS.mouthOpenness,
    ),
  };
}

function expressionControlLabel(value: number): string {
  if (value === 0) return "Original";
  return `${value > 0 ? "+" : ""}${Math.round(value * 100)}%`;
}

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

function storeExpressionControls(controls: ExpressionControls): void {
  const session = getStoredSession();
  if (!session) return;
  storeSession({
    ...session,
    eyeOpenness: controls.eyeOpenness,
    mouthOpenness: controls.mouthOpenness,
  });
}

function storePortraitId(portraitId: string): void {
  const session = getStoredSession();
  if (!session) return;
  storeSession({ ...session, portraitId });
}

async function publishExpressionControls(
  room: Room,
  controls: ExpressionControls,
): Promise<void> {
  const message = JSON.stringify({
    type: "update_expression_controls",
    eye_openness: controls.eyeOpenness,
    mouth_openness: controls.mouthOpenness,
  });
  await room.localParticipant.publishData(
    new TextEncoder().encode(message),
    { reliable: true },
  );
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
  const [viewerCredentials, setViewerCredentials] = useState<ViewerCredentials | null>(null);
  const [credentialsCopied, setCredentialsCopied] = useState(false);
  const [broadcastStatus, setBroadcastStatus] = useState<BroadcastStatus>("idle");
  const [broadcastError, setBroadcastError] = useState("");
  const [broadcastRotation, setBroadcastRotation] = useState<BroadcastRotation>(90);
  const [broadcastViewport, setBroadcastViewport] = useState<BroadcastViewport>(
    DEFAULT_BROADCAST_VIEWPORT,
  );
  const [rtspCopied, setRtspCopied] = useState(false);
  const [outputReady, setOutputReady] = useState(false);
  const [expressionControls, setExpressionControls] = useState<ExpressionControls>(
    DEFAULT_EXPRESSION_CONTROLS,
  );
  const roomRef = useRef<Room | null>(null);
  const cameraTrackRef = useRef<LocalVideoTrack | null>(null);
  const outputTrackRef = useRef<RemoteVideoTrack | null>(null);
  const publisherRef = useRef<VideoWhipPublisher | null>(null);
  const broadcastRotationRef = useRef<BroadcastRotation>(90);
  const broadcastViewportRef = useRef<BroadcastViewport>(DEFAULT_BROADCAST_VIEWPORT);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const outputVideoRef = useRef<HTMLVideoElement>(null);
  const sessionInfoRef = useRef<{ sessionId: string; podId: string | null } | null>(null);
  const currentPortraitIdRef = useRef<string>("");
  const workerWaitTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const expressionControlsTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const expressionControlsRef = useRef<ExpressionControls>(DEFAULT_EXPRESSION_CONTROLS);

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
        setPortraitId((current) => current || page.items[0]?.id || "");
      })
      .catch(() => setError("Could not load portraits."));
  }, []);

  const copyViewerCredentials = useCallback(async () => {
    if (!viewerCredentials) return;

    const payload = serializeViewerCredentials(viewerCredentials, true);

    try {
      await navigator.clipboard.writeText(payload);
      setCredentialsCopied(true);
    } catch (caught) {
      console.error("Failed to copy viewer credentials:", caught);
      setError("Could not copy the app credentials.");
    }
  }, [viewerCredentials]);

  const stopBroadcast = useCallback(async () => {
    const publisher = publisherRef.current;
    if (!publisher) return;

    await publisher.stop();
    if (publisherRef.current === publisher) publisherRef.current = null;
    setRtspCopied(false);
  }, []);

  const setBroadcastRotationBoth = useCallback((rotation: BroadcastRotation) => {
    broadcastRotationRef.current = rotation;
    setBroadcastRotation(rotation);
    publisherRef.current?.setRotation(rotation);
  }, []);

  const setBroadcastViewportBoth = useCallback((viewport: BroadcastViewport) => {
    const nextViewport = {
      zoom: Math.min(MAX_BROADCAST_ZOOM, Math.max(MIN_BROADCAST_ZOOM, viewport.zoom)),
      panX: Math.min(1, Math.max(-1, viewport.panX)),
      panY: Math.min(1, Math.max(-1, viewport.panY)),
    };
    if (nextViewport.zoom === MIN_BROADCAST_ZOOM) {
      nextViewport.panX = 0;
      nextViewport.panY = 0;
    }

    broadcastViewportRef.current = nextViewport;
    setBroadcastViewport(nextViewport);
    publisherRef.current?.setViewport(nextViewport);
  }, []);

  const setBroadcastZoom = useCallback((zoom: number) => {
    setBroadcastViewportBoth({ ...broadcastViewportRef.current, zoom });
  }, [setBroadcastViewportBoth]);

  const setBroadcastPan = useCallback((panX: number, panY: number) => {
    setBroadcastViewportBoth({ ...broadcastViewportRef.current, panX, panY });
  }, [setBroadcastViewportBoth]);

  const resetBroadcastViewport = useCallback(() => {
    setBroadcastViewportBoth(DEFAULT_BROADCAST_VIEWPORT);
  }, [setBroadcastViewportBoth]);

  const startBroadcast = useCallback(async () => {
    const outputVideo = outputVideoRef.current;
    if (!MEDIA_MTX_ENDPOINTS) {
      setBroadcastError("MediaMTX is not configured for this web deployment.");
      return;
    }
    if (
      !isLive ||
      !outputTrackRef.current ||
      !outputReady ||
      !outputVideo ||
      outputVideo.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
      outputVideo.videoWidth < 1 ||
      outputVideo.videoHeight < 1
    ) {
      setBroadcastError("Wait for the processed output to decode a video frame.");
      return;
    }

    await stopBroadcast();
    setBroadcastError("");
    setRtspCopied(false);

    const publisher = new VideoWhipPublisher(outputVideo, {
      endpoint: MEDIA_MTX_ENDPOINTS.whipUrl,
      width: BROADCAST_WIDTH,
      height: BROADCAST_HEIGHT,
      frameRate: 30,
      rotation: broadcastRotationRef.current,
      onStatusChange: (nextStatus, nextError) => {
        if (publisherRef.current !== publisher) return;
        setBroadcastStatus(nextStatus);
        setBroadcastError(nextError?.message ?? "");
      },
    });
    publisher.setViewport(broadcastViewportRef.current);
    publisherRef.current = publisher;

    try {
      await publisher.start();
    } catch {
      // The publisher reports actionable failures through onStatusChange.
    }
  }, [isLive, outputReady, stopBroadcast]);

  const copyRtspUrl = useCallback(async () => {
    if (!MEDIA_MTX_ENDPOINTS) return;

    try {
      await navigator.clipboard.writeText(MEDIA_MTX_ENDPOINTS.rtspUrl);
      setRtspCopied(true);
    } catch (caught) {
      console.error("Failed to copy RTSP URL:", caught);
      setBroadcastError("Could not copy the RTSP URL. Select it manually instead.");
    }
  }, []);

  const stop = useCallback(async () => {
    if (workerWaitTimeoutRef.current) {
      clearTimeout(workerWaitTimeoutRef.current);
      workerWaitTimeoutRef.current = null;
    }
    if (expressionControlsTimeoutRef.current) {
      clearTimeout(expressionControlsTimeoutRef.current);
      expressionControlsTimeoutRef.current = null;
    }

    await stopBroadcast();

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
    setViewerCredentials(null);
    setCredentialsCopied(false);
    setOutputReady(false);
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
  }, [stopBroadcast]);

  const syncExpressionControls = useCallback(
    (room: Room, controls = expressionControlsRef.current) => {
      void publishExpressionControls(room, controls).catch((caught) => {
        console.error("Failed to update expression controls:", caught);
        setError("Could not update the live expression controls.");
      });
    },
    [],
  );

  const registerRoomListeners = useCallback((room: Room) => {
    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
      if (roomRef.current !== room || track.kind !== Track.Kind.Video) return;

      const videoTrack = track as RemoteVideoTrack;
      outputTrackRef.current = videoTrack;
      setOutputReady(false);
      if (outputVideoRef.current) videoTrack.attach(outputVideoRef.current);
      if (workerWaitTimeoutRef.current) {
        clearTimeout(workerWaitTimeoutRef.current);
        workerWaitTimeoutRef.current = null;
      }
      setStatus("Live");
      setReconnecting(false);
      syncExpressionControls(room);
    });

    room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
      if (roomRef.current !== room || track !== outputTrackRef.current) return;

      outputTrackRef.current = null;
      setOutputReady(false);
      void stopBroadcast();
      setStatus("Processed output unavailable.");
    });

    room.on(RoomEvent.Disconnected, () => {
      if (roomRef.current !== room) return;
      if (workerWaitTimeoutRef.current) {
        clearTimeout(workerWaitTimeoutRef.current);
        workerWaitTimeoutRef.current = null;
      }
      outputTrackRef.current = null;
      setOutputReady(false);
      setViewerCredentials(null);
      setCredentialsCopied(false);
      setReconnecting(false);
      clearStoredSession();
      void stopBroadcast();
      setStatus("Disconnected.");
    });
  }, [stopBroadcast, syncExpressionControls]);

  const updateExpressionControls = useCallback((controls: ExpressionControls) => {
    expressionControlsRef.current = controls;
    setExpressionControls(controls);
    storeExpressionControls(controls);

    if (expressionControlsTimeoutRef.current) {
      clearTimeout(expressionControlsTimeoutRef.current);
    }
    expressionControlsTimeoutRef.current = setTimeout(() => {
      expressionControlsTimeoutRef.current = null;
      const room = roomRef.current;
      if (room && outputTrackRef.current) syncExpressionControls(room);
    }, EXPRESSION_CONTROLS_DEBOUNCE_MS);
  }, [syncExpressionControls]);

  const resetExpressionControls = useCallback(() => {
    updateExpressionControls(DEFAULT_EXPRESSION_CONTROLS);
  }, [updateExpressionControls]);

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
    setOutputReady(false);
    setError("");

    try {
      const restoredControls = expressionControlsFromSession(stored);
      expressionControlsRef.current = restoredControls;
      setExpressionControls(restoredControls);
      sessionInfoRef.current = { sessionId: stored.sessionId, podId: stored.podId };
      currentPortraitIdRef.current = stored.portraitId;

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      registerRoomListeners(room);

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
  }, [registerRoomListeners, stop, waitForWorker]);

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
    setError("");

    try {
      // Refresh the portrait so the worker receives a newly signed download URL.
      const portrait = await getPortrait(newPortraitId);

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
      storePortraitId(newPortraitId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to change portrait.");
    } finally {
      setChangingPortrait(false);
    }
  };

  const start = async () => {
    if (!portraitId || connecting || roomRef.current) return;
    setConnecting(true);
    setOutputReady(false);
    setError("");
    setStatus("Connecting…");

    try {
      const session = await createRealtimeSession(portraitId);
      sessionInfoRef.current = { sessionId: session.session_id, podId: session.pod_id ?? null };
      currentPortraitIdRef.current = portraitId;

      // Store session for reconnection
      const expiresAt = Date.now() + (session.expires_in_seconds * 1000);
      setViewerCredentials({
        wsUrl: session.server_url,
        roomId: session.room_name,
        accessToken: session.viewer_token,
        expiresInSeconds: session.expires_in_seconds,
      });
      setCredentialsCopied(false);
      storeSession({
        sessionId: session.session_id,
        podId: session.pod_id ?? null,
        roomName: session.room_name,
        serverUrl: session.server_url,
        participantToken: session.participant_token,
        portraitId: portraitId,
        expiresAt: expiresAt,
        eyeOpenness: expressionControlsRef.current.eyeOpenness,
        mouthOpenness: expressionControlsRef.current.mouthOpenness,
      });

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      registerRoomListeners(room);

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
          <video
            ref={outputVideoRef}
            autoPlay
            playsInline
            onLoadedData={() => setOutputReady(true)}
            onEmptied={() => setOutputReady(false)}
            className="main-live-video"
          />
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
          <div className="live-control-group expression-controls" aria-labelledby="expression-controls-title">
            <div className="expression-controls-heading">
              <div>
                <h4 id="expression-controls-title">Expression balance</h4>
                <p>Fine-tune the portrait while live.</p>
              </div>
              <button
                type="button"
                className="expression-reset"
                onClick={resetExpressionControls}
                disabled={reconnecting}
              >
                Reset adjustments
              </button>
            </div>

            <div className="expression-slider">
              <div className="expression-slider-header">
                <label htmlFor="eye-openness">Eye openness</label>
                <output htmlFor="eye-openness">
                  {expressionControlLabel(expressionControls.eyeOpenness)}
                </output>
              </div>
              <input
                id="eye-openness"
                type="range"
                min="-1"
                max="1"
                step="0.05"
                value={expressionControls.eyeOpenness}
                onChange={(event) => updateExpressionControls({
                  ...expressionControlsRef.current,
                  eyeOpenness: Number(event.target.value),
                })}
                disabled={reconnecting}
              />
              <div className="expression-slider-scale" aria-hidden="true">
                <span>More closed</span>
                <span>More open</span>
              </div>
            </div>

            <div className="expression-slider">
              <div className="expression-slider-header">
                <label htmlFor="mouth-openness">Mouth openness</label>
                <output htmlFor="mouth-openness">
                  {expressionControlLabel(expressionControls.mouthOpenness)}
                </output>
              </div>
              <input
                id="mouth-openness"
                type="range"
                min="-1"
                max="1"
                step="0.05"
                value={expressionControls.mouthOpenness}
                onChange={(event) => updateExpressionControls({
                  ...expressionControlsRef.current,
                  mouthOpenness: Number(event.target.value),
                })}
                disabled={reconnecting}
              />
              <div className="expression-slider-scale" aria-hidden="true">
                <span>More closed</span>
                <span>More open</span>
              </div>
            </div>
          </div>
          <BroadcastControls
            endpoints={MEDIA_MTX_ENDPOINTS}
            status={broadcastStatus}
            rotation={broadcastRotation}
            viewport={broadcastViewport}
            error={broadcastError}
            copied={rtspCopied}
            canStart={Boolean(
              MEDIA_MTX_ENDPOINTS &&
              isLive &&
              outputReady &&
              !reconnecting &&
              !publisherRef.current &&
              broadcastStatus !== "connecting" &&
              broadcastStatus !== "stopping" &&
              broadcastStatus !== "live"
            )}
            hasPublisher={Boolean(publisherRef.current)}
            onStart={() => void startBroadcast()}
            onStop={() => void stopBroadcast()}
            onCopy={() => void copyRtspUrl()}
            onRotationChange={setBroadcastRotationBoth}
            onZoomChange={setBroadcastZoom}
            onPanChange={setBroadcastPan}
            onViewportReset={resetBroadcastViewport}
          />
          {viewerCredentials && (
            <ViewerCredentialsPanel
              credentials={viewerCredentials}
              copied={credentialsCopied}
              onCopy={() => void copyViewerCredentials()}
            />
          )}
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
        {viewerCredentials && (
          <ViewerCredentialsPanel
            credentials={viewerCredentials}
            copied={credentialsCopied}
            onCopy={() => void copyViewerCredentials()}
          />
        )}
        <p role="status">{status}</p>
        {error && <p className="error" role="alert">{error}</p>}
        {!portraits.length && <p><a href="/portraits">Upload a portrait first.</a></p>}
      </div>

      <div className="realtime-videos">
        <figure><video ref={localVideoRef} autoPlay muted playsInline /><figcaption>Camera</figcaption></figure>
        <figure>
          <video
            ref={outputVideoRef}
            autoPlay
            playsInline
            onLoadedData={() => setOutputReady(true)}
            onEmptied={() => setOutputReady(false)}
          />
          <figcaption>Processed output</figcaption>
        </figure>
      </div>
    </section>
  );
}
