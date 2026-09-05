export type BroadcastStatus = "idle" | "connecting" | "live" | "stopping" | "error";

/**
 * The relay canvas is a 2K square, so the broadcast keeps a 1:1 aspect ratio
 * regardless of the source orientation or the 90/270 degree rotations that swap
 * the logical axes. `containRect` letterboxes the source inside it.
 */
export const BROADCAST_WIDTH = 2048;
export const BROADCAST_HEIGHT = 2048;

export interface VideoWhipPublisherOptions {
  endpoint: string;
  width?: number;
  height?: number;
  frameRate?: number;
  backgroundColor?: string;
  connectionTimeoutMs?: number;
  rotation?: BroadcastRotation;
  onStatusChange?: (status: BroadcastStatus, error?: Error) => void;
}

export interface MediaMtxEndpoints {
  host: string;
  whipUrl: string;
  whepUrl: string;
  rtspUrl: string;
}

export interface ContainRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface NormalizedOptions {
  endpoint: string;
  width: number;
  height: number;
  frameRate: number;
  backgroundColor: string;
  connectionTimeoutMs: number;
  onStatusChange?: (status: BroadcastStatus, error?: Error) => void;
}

interface CodecCapabilityWithPayloadType extends RTCRtpCodec {
  preferredPayloadType?: number;
}

export type BroadcastRotation = 0 | 90 | 180 | 270;

export interface BroadcastViewport {
  zoom: number;
  panX: number;
  panY: number;
}

export const MIN_BROADCAST_ZOOM = 1;
export const MAX_BROADCAST_ZOOM = 5;

const DEFAULT_BROADCAST_VIEWPORT: BroadcastViewport = {
  zoom: MIN_BROADCAST_ZOOM,
  panX: 0,
  panY: 0,
};

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function containRect(
  sourceWidth: number,
  sourceHeight: number,
  outputWidth: number,
  outputHeight: number,
): ContainRect {
  if (
    !Number.isFinite(sourceWidth) ||
    !Number.isFinite(sourceHeight) ||
    !Number.isFinite(outputWidth) ||
    !Number.isFinite(outputHeight) ||
    sourceWidth <= 0 ||
    sourceHeight <= 0 ||
    outputWidth <= 0 ||
    outputHeight <= 0
  ) {
    throw new RangeError("Video dimensions must be finite positive numbers.");
  }

  const scale = Math.min(outputWidth / sourceWidth, outputHeight / sourceHeight);
  const width = sourceWidth * scale;
  const height = sourceHeight * scale;

  return {
    x: (outputWidth - width) / 2,
    y: (outputHeight - height) / 2,
    width,
    height,
  };
}

export function getMediaMtxEndpoints(rawHost: string | undefined): MediaMtxEndpoints | null {
  const host = rawHost?.trim();
  if (!host || host.length > 253 || /[\s/:@?#\\]/.test(host)) return null;

  if (/^[\d.]+$/.test(host)) {
    const octets = host.split(".");
    if (
      octets.length !== 4 ||
      octets.some((octet) => !/^\d{1,3}$/.test(octet) || Number(octet) > 255)
    ) {
      return null;
    }
  } else {
    const labels = host.split(".");
    if (
      labels.some(
        (label) =>
          !label ||
          label.length > 63 ||
          !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i.test(label),
      )
    ) {
      return null;
    }
  }

  return {
    host,
    whipUrl: `http://${host}:8889/mimicmotion/whip`,
    whepUrl: `http://${host}:8889/mimicmotion/`,
    rtspUrl: `rtsp://${host}:8554/mimicmotion`,
  };
}

export class VideoWhipPublisher {
  private readonly options: NormalizedOptions;

  private status: BroadcastStatus = "idle";
  private operation = 0;
  private peerConnection: RTCPeerConnection | null = null;
  private relayCanvas: HTMLCanvasElement | null = null;
  private relayContext: CanvasRenderingContext2D | null = null;
  private mediaStream: MediaStream | null = null;
  private videoFrameCallback = 0;
  private animationFrame = 0;
  private abortController: AbortController | null = null;
  private resourceUrl: string | null = null;
  private heartbeat = false;
  private lastFrameTime: number | null = null;
  private rotation: BroadcastRotation;
  private viewport: BroadcastViewport = { ...DEFAULT_BROADCAST_VIEWPORT };

  constructor(
    private readonly sourceVideo: HTMLVideoElement,
    options: VideoWhipPublisherOptions,
  ) {
    this.options = {
      endpoint: options.endpoint,
      width: options.width ?? BROADCAST_WIDTH,
      height: options.height ?? BROADCAST_HEIGHT,
      frameRate: options.frameRate ?? 30,
      backgroundColor: options.backgroundColor ?? "#000000",
      connectionTimeoutMs: options.connectionTimeoutMs ?? 15_000,
      onStatusChange: options.onStatusChange,
    };
    this.rotation = options.rotation ?? 90;
  }

  getStatus(): BroadcastStatus {
    return this.status;
  }

  getRotation(): BroadcastRotation {
    return this.rotation;
  }

  // Rotation only affects the relay canvas draw, so it can change mid-broadcast
  // without renegotiating the WHIP session.
  setRotation(rotation: BroadcastRotation): void {
    if (this.rotation === rotation) return;
    this.rotation = rotation;
    this.drawSourceFrame();
  }

  getViewport(): BroadcastViewport {
    return { ...this.viewport };
  }

  // Pan values are normalized to -1..1 so the same framing works at any
  // broadcast resolution. Positive values move the rendered frame right/down.
  setViewport(viewport: BroadcastViewport): void {
    const zoom = Number.isFinite(viewport.zoom)
      ? clamp(viewport.zoom, MIN_BROADCAST_ZOOM, MAX_BROADCAST_ZOOM)
      : MIN_BROADCAST_ZOOM;
    const panX = Number.isFinite(viewport.panX) ? clamp(viewport.panX, -1, 1) : 0;
    const panY = Number.isFinite(viewport.panY) ? clamp(viewport.panY, -1, 1) : 0;
    const nextViewport = zoom === MIN_BROADCAST_ZOOM
      ? { zoom, panX: 0, panY: 0 }
      : { zoom, panX, panY };

    if (
      this.viewport.zoom === nextViewport.zoom &&
      this.viewport.panX === nextViewport.panX &&
      this.viewport.panY === nextViewport.panY
    ) {
      return;
    }

    this.viewport = nextViewport;
    this.drawSourceFrame();
  }

  resetViewport(): void {
    this.setViewport(DEFAULT_BROADCAST_VIEWPORT);
  }

  async start(): Promise<void> {
    if (
      this.status === "connecting" ||
      this.status === "live" ||
      this.status === "stopping"
    ) {
      return;
    }

    const operation = ++this.operation;
    const abortController = new AbortController();
    this.abortController = abortController;
    this.setStatus("connecting");

    try {
      this.assertBrowserSupport();
      this.startVideoCapture();

      const stream = this.mediaStream;
      const videoTrack = stream?.getVideoTracks()[0];
      if (!stream || !videoTrack) {
        throw new Error("The browser did not create a video track from the relay canvas.");
      }

      const peerConnection = new RTCPeerConnection();
      this.peerConnection = peerConnection;
      peerConnection.addEventListener("connectionstatechange", this.onConnectionStateChange);

      const transceiver = peerConnection.addTransceiver(videoTrack, {
        direction: "sendonly",
        streams: [stream],
      });
      this.preferH264(transceiver);

      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);
      await this.waitForIceGathering(peerConnection, operation, abortController.signal);
      this.assertCurrent(operation);

      const localDescription = peerConnection.localDescription;
      if (!localDescription?.sdp) {
        throw new Error("WebRTC did not produce a local SDP offer.");
      }

      const response = await this.publishOffer(localDescription.sdp, abortController.signal);
      const location = response.headers.get("Location");
      if (location) this.resourceUrl = new URL(location, this.options.endpoint).href;

      const answer = (await response.text()).trim();
      if (!answer) throw new Error("MediaMTX returned an empty SDP answer.");
      this.assertCurrent(operation);

      // MediaMTX can include a redundant RTCP component candidate even with
      // rtcp-mux; Chromium rejects that answer instead of ignoring the line.
      const compatibleAnswer = answer
        .replace(/^a=candidate:\S+\s+2\s+[^\r\n]*(?:\r?\n|$)/gm, "")
        .replace(/(^|\r\n|\n)a=end-of-candidates$/, "$1");
      await peerConnection.setRemoteDescription({ type: "answer", sdp: compatibleAnswer });
      await this.waitForConnection(peerConnection, operation, abortController.signal);
      this.assertCurrent(operation);
      this.setStatus("live");
    } catch (cause) {
      if (operation !== this.operation) return;

      const error = this.toBroadcastError(cause);
      const failureOperation = ++this.operation;
      await this.releaseResources(true);
      if (failureOperation !== this.operation) return;

      this.setStatus("error", error);
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (
      this.status === "idle" &&
      !this.peerConnection &&
      !this.mediaStream &&
      !this.resourceUrl
    ) {
      return;
    }

    ++this.operation;
    this.setStatus("stopping");
    await this.releaseResources(true);
    this.setStatus("idle");
  }

  private assertBrowserSupport(): void {
    if (typeof RTCPeerConnection === "undefined") {
      throw new Error("This browser does not support WebRTC publishing.");
    }
    if (
      typeof HTMLCanvasElement === "undefined" ||
      typeof HTMLCanvasElement.prototype.captureStream !== "function"
    ) {
      throw new Error("This browser cannot capture video from an HTML canvas.");
    }
    if (
      typeof RTCRtpSender === "undefined" ||
      typeof RTCRtpSender.getCapabilities !== "function"
    ) {
      throw new Error("This browser cannot report its WebRTC video codecs.");
    }
    if (
      typeof RTCRtpTransceiver === "undefined" ||
      typeof RTCRtpTransceiver.prototype.setCodecPreferences !== "function"
    ) {
      throw new Error("This browser cannot select the H.264 broadcast codec.");
    }
    if (
      !Number.isFinite(this.options.width) ||
      !Number.isFinite(this.options.height) ||
      !Number.isFinite(this.options.frameRate) ||
      this.options.width < 1 ||
      this.options.height < 1 ||
      this.options.frameRate < 1
    ) {
      throw new Error("Broadcast width, height, and frame rate must be positive.");
    }

    const readyState = this.sourceVideo.readyState;
    if (
      readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
      this.sourceVideo.videoWidth < 1 ||
      this.sourceVideo.videoHeight < 1
    ) {
      throw new Error("The processed output has not decoded a video frame yet.");
    }
  }

  private startVideoCapture(): void {
    const relayCanvas = document.createElement("canvas");
    relayCanvas.width = Math.round(this.options.width);
    relayCanvas.height = Math.round(this.options.height);
    this.relayCanvas = relayCanvas;

    const context = relayCanvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("Could not create the broadcast relay canvas.");
    this.relayContext = context;

    if (!this.drawSourceFrame()) {
      throw new Error("The processed output has not decoded a video frame yet.");
    }

    const stream = relayCanvas.captureStream(this.options.frameRate);
    this.mediaStream = stream;
    const videoTrack = stream.getVideoTracks()[0];
    if (!videoTrack) throw new Error("The browser did not create a canvas video track.");
    videoTrack.contentHint = "motion";

    this.lastFrameTime = performance.now();
    this.scheduleFrameCopy();
  }

  private scheduleFrameCopy(): void {
    const sourceWithVideoFrames = this.sourceVideo as HTMLVideoElement & {
      requestVideoFrameCallback?: (callback: VideoFrameRequestCallback) => number;
    };

    if (typeof sourceWithVideoFrames.requestVideoFrameCallback === "function") {
      this.videoFrameCallback = sourceWithVideoFrames.requestVideoFrameCallback((time) => {
        this.videoFrameCallback = 0;
        if (!this.relayCanvas) return;
        this.copyFrameAt(time);
        this.scheduleFrameCopy();
      });
      return;
    }

    this.animationFrame = window.requestAnimationFrame((time) => {
      this.animationFrame = 0;
      if (!this.relayCanvas) return;
      this.copyFrameAt(time);
      this.scheduleFrameCopy();
    });
  }

  private copyFrameAt(time: number): void {
    const frameInterval = 1000 / this.options.frameRate;
    if (this.lastFrameTime !== null && time - this.lastFrameTime < frameInterval) return;

    if (this.drawSourceFrame()) {
      this.lastFrameTime =
        this.lastFrameTime === null
          ? time
          : time - ((time - this.lastFrameTime) % frameInterval);
    }
  }

  private drawSourceFrame(): boolean {
    const context = this.relayContext;
    const relayCanvas = this.relayCanvas;
    const sourceWidth = this.sourceVideo.videoWidth;
    const sourceHeight = this.sourceVideo.videoHeight;
    const rotation = this.rotation;
    if (!context || !relayCanvas || sourceWidth < 1 || sourceHeight < 1) return false;

    const swapAxes = rotation === 90 || rotation === 270;
    const logicalWidth = swapAxes ? sourceHeight : sourceWidth;
    const logicalHeight = swapAxes ? sourceWidth : sourceHeight;
    const rect = containRect(
      logicalWidth,
      logicalHeight,
      relayCanvas.width,
      relayCanvas.height,
    );

    context.fillStyle = this.options.backgroundColor;
    context.fillRect(0, 0, relayCanvas.width, relayCanvas.height);

    const { zoom, panX, panY } = this.viewport;
    const hasViewportTransform = zoom !== MIN_BROADCAST_ZOOM || panX !== 0 || panY !== 0;
    if (hasViewportTransform) {
      const maxPanX = (relayCanvas.width * (zoom - 1)) / 2;
      const maxPanY = (relayCanvas.height * (zoom - 1)) / 2;
      context.save();
      context.beginPath();
      context.rect(0, 0, relayCanvas.width, relayCanvas.height);
      context.clip();
      context.translate(
        relayCanvas.width / 2 + panX * maxPanX,
        relayCanvas.height / 2 + panY * maxPanY,
      );
      context.scale(zoom, zoom);
      context.translate(-relayCanvas.width / 2, -relayCanvas.height / 2);
    }

    if (rotation === 0) {
      context.drawImage(this.sourceVideo, rect.x, rect.y, rect.width, rect.height);
    } else {
      const radians =
        rotation === 90
          ? Math.PI / 2
          : rotation === 180
            ? Math.PI
            : -Math.PI / 2;
      context.save();
      context.translate(relayCanvas.width / 2, relayCanvas.height / 2);
      context.rotate(radians);
      context.drawImage(
        this.sourceVideo,
        -rect.width / 2,
        -rect.height / 2,
        rect.width,
        rect.height,
      );
      context.restore();
    }

    if (hasViewportTransform) context.restore();

    this.heartbeat = !this.heartbeat;
    context.fillStyle = this.heartbeat ? "#000000" : "#ffffff";
    context.fillRect(relayCanvas.width - 2, relayCanvas.height - 2, 2, 2);
    return true;
  }

  private preferH264(transceiver: RTCRtpTransceiver): void {
    const capabilities = RTCRtpSender.getCapabilities("video");
    const codecs = capabilities?.codecs as CodecCapabilityWithPayloadType[] | undefined;
    const h264Codecs = codecs?.filter(
      (codec) => codec.mimeType.toLowerCase() === "video/h264",
    );

    if (!h264Codecs?.length) {
      throw new Error("This browser does not expose an H.264 WebRTC encoder required for RTSP.");
    }

    const h264PayloadTypes = new Set(
      h264Codecs
        .map((codec) => codec.preferredPayloadType)
        .filter((payloadType): payloadType is number => payloadType !== undefined),
    );
    const associatedRtx = codecs?.filter((codec) => {
      if (codec.mimeType.toLowerCase() !== "video/rtx" || !codec.sdpFmtpLine) return false;
      const apt = /(?:^|;)\s*apt=(\d+)(?:;|$)/i.exec(codec.sdpFmtpLine)?.[1];
      return apt !== undefined && h264PayloadTypes.has(Number(apt));
    }) ?? [];

    transceiver.setCodecPreferences([...h264Codecs, ...associatedRtx]);
  }

  private async publishOffer(sdp: string, signal: AbortSignal): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(this.options.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: sdp,
        signal,
      });
    } catch (cause) {
      if (cause instanceof Error && cause.name === "AbortError") throw cause;
      throw new Error(
        "Could not reach MediaMTX. Confirm Docker is running and TCP port 8889 is available.",
        { cause },
      );
    }

    if (!response.ok) {
      const detail = (await response.text()).trim();
      throw new Error(
        `MediaMTX rejected the broadcast (${response.status}${detail ? `: ${detail}` : ""}).`,
      );
    }
    return response;
  }

  private waitForIceGathering(
    peerConnection: RTCPeerConnection,
    operation: number,
    signal: AbortSignal,
  ): Promise<void> {
    if (peerConnection.iceGatheringState === "complete") return Promise.resolve();

    return this.waitForPeerState(
      peerConnection,
      "icegatheringstatechange",
      operation,
      signal,
      () => peerConnection.iceGatheringState === "complete",
      () => null,
      "Timed out while gathering WebRTC network candidates.",
    );
  }

  private waitForConnection(
    peerConnection: RTCPeerConnection,
    operation: number,
    signal: AbortSignal,
  ): Promise<void> {
    if (peerConnection.connectionState === "connected") return Promise.resolve();

    return this.waitForPeerState(
      peerConnection,
      "connectionstatechange",
      operation,
      signal,
      () => peerConnection.connectionState === "connected",
      () =>
        peerConnection.connectionState === "failed"
          ? new Error("The WebRTC connection to MediaMTX failed.")
          : null,
      "Timed out connecting to MediaMTX. Check the LAN IP, UDP port 8189, and Windows Firewall.",
    );
  }

  private waitForPeerState(
    peerConnection: RTCPeerConnection,
    eventName: "icegatheringstatechange" | "connectionstatechange",
    operation: number,
    signal: AbortSignal,
    isComplete: () => boolean,
    getFailure: () => Error | null,
    timeoutMessage: string,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        cleanup();
        reject(new Error(timeoutMessage));
      }, this.options.connectionTimeoutMs);

      const onAbort = () => {
        cleanup();
        reject(new DOMException("Broadcast cancelled.", "AbortError"));
      };
      const onStateChange = () => {
        if (operation !== this.operation) {
          onAbort();
          return;
        }
        const failure = getFailure();
        if (failure) {
          cleanup();
          reject(failure);
        } else if (isComplete()) {
          cleanup();
          resolve();
        }
      };
      const cleanup = () => {
        window.clearTimeout(timeout);
        peerConnection.removeEventListener(eventName, onStateChange);
        signal.removeEventListener("abort", onAbort);
      };

      peerConnection.addEventListener(eventName, onStateChange);
      signal.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted) onAbort();
      else onStateChange();
    });
  }

  private onConnectionStateChange = (): void => {
    if (this.status !== "live" || this.peerConnection?.connectionState !== "failed") return;

    const error = new Error("The WebRTC connection to MediaMTX was lost.");
    const failureOperation = ++this.operation;
    void this.releaseResources(true).then(() => {
      if (failureOperation === this.operation) this.setStatus("error", error);
    });
  };

  private assertCurrent(operation: number): void {
    if (operation !== this.operation) {
      throw new DOMException("Broadcast cancelled.", "AbortError");
    }
  }

  private async releaseResources(deleteRemote: boolean): Promise<void> {
    this.abortController?.abort();
    this.abortController = null;

    const deleteRequest = deleteRemote ? this.deleteResource() : Promise.resolve();

    if (this.peerConnection) {
      this.peerConnection.removeEventListener(
        "connectionstatechange",
        this.onConnectionStateChange,
      );
      this.peerConnection.close();
      this.peerConnection = null;
    }

    const sourceWithVideoFrames = this.sourceVideo as HTMLVideoElement & {
      cancelVideoFrameCallback?: (handle: number) => void;
    };
    if (this.videoFrameCallback) {
      sourceWithVideoFrames.cancelVideoFrameCallback?.(this.videoFrameCallback);
      this.videoFrameCallback = 0;
    }
    if (this.animationFrame) {
      window.cancelAnimationFrame(this.animationFrame);
      this.animationFrame = 0;
    }

    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.mediaStream = null;
    this.relayContext = null;
    this.relayCanvas = null;
    this.lastFrameTime = null;

    await deleteRequest;
  }

  private async deleteResource(): Promise<void> {
    const resourceUrl = this.resourceUrl;
    this.resourceUrl = null;
    if (!resourceUrl) return;

    try {
      await fetch(resourceUrl, { method: "DELETE" });
    } catch {
      // Closing the peer connection still stops publication; MediaMTX expires it.
    }
  }

  private toBroadcastError(cause: unknown): Error {
    if (cause instanceof Error && cause.name !== "AbortError") return cause;
    return new Error("The broadcast could not be started.");
  }

  private setStatus(status: BroadcastStatus, error?: Error): void {
    this.status = status;
    this.options.onStatusChange?.(status, error);
  }
}
