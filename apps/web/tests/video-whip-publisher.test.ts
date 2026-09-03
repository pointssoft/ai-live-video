import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  containRect,
  getMediaMtxEndpoints,
  VideoWhipPublisher,
  type BroadcastStatus,
} from "@/lib/video-whip-publisher";

class FakeTransceiver {
  setCodecPreferencesMock = vi.fn();

  setCodecPreferences(codecs: RTCRtpCodec[]): void {
    this.setCodecPreferencesMock(codecs);
  }
}

class FakePeerConnection extends EventTarget {
  static instances: FakePeerConnection[] = [];
  static initialIceGatheringState: RTCIceGatheringState = "complete";

  iceGatheringState: RTCIceGatheringState = FakePeerConnection.initialIceGatheringState;
  connectionState: RTCPeerConnectionState = "connected";
  localDescription: RTCSessionDescription | null = {
    type: "offer",
    sdp: "v=0\r\n",
    toJSON: () => ({ type: "offer", sdp: "v=0\r\n" }),
  };
  transceiver = new FakeTransceiver();
  addTransceiver = vi.fn(() => this.transceiver);
  createOffer = vi.fn(async () => ({ type: "offer" as const, sdp: "v=0\r\n" }));
  setLocalDescription = vi.fn(async () => undefined);
  setRemoteDescription = vi.fn(async () => undefined);
  close = vi.fn();

  constructor() {
    super();
    FakePeerConnection.instances.push(this);
  }
}

const context = {
  fillStyle: "",
  fillRect: vi.fn(),
  drawImage: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  rotate: vi.fn(),
};
const relayTrack = {
  contentHint: "",
  stop: vi.fn(),
};
const relayStream = {
  getVideoTracks: vi.fn(() => [relayTrack]),
  getTracks: vi.fn(() => [relayTrack]),
};
const frameCallbacks = new Map<number, VideoFrameRequestCallback>();
let nextFrameCallback = 1;
let captureStream: ReturnType<typeof vi.fn>;
let getContext: { mockRestore: () => void };
let originalCaptureStream: PropertyDescriptor | undefined;

function createReadyVideo(width = 720, height = 1280): HTMLVideoElement {
  const video = document.createElement("video");
  Object.defineProperties(video, {
    readyState: { configurable: true, value: HTMLMediaElement.HAVE_CURRENT_DATA },
    videoWidth: { configurable: true, value: width },
    videoHeight: { configurable: true, value: height },
    requestVideoFrameCallback: {
      configurable: true,
      value: vi.fn((callback: VideoFrameRequestCallback) => {
        const id = nextFrameCallback++;
        frameCallbacks.set(id, callback);
        return id;
      }),
    },
    cancelVideoFrameCallback: {
      configurable: true,
      value: vi.fn((id: number) => frameCallbacks.delete(id)),
    },
  });
  return video;
}

function successfulFetch() {
  return vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "DELETE") return new Response(null, { status: 204 });
    return new Response(
      [
        "v=0",
        "a=rtcp-mux",
        "a=candidate:123 1 udp 2130706431 192.168.0.106 8189 typ host",
        "a=candidate:123 2 udp 2130706431 192.168.0.106 8189 typ host",
        "a=end-of-candidates",
      ].join("\r\n"),
      {
        status: 201,
        headers: { Location: "/mimicmotion/whip/session-id" },
      },
    );
  });
}

beforeEach(() => {
  FakePeerConnection.instances = [];
  FakePeerConnection.initialIceGatheringState = "complete";
  frameCallbacks.clear();
  nextFrameCallback = 1;
  context.fillStyle = "";
  context.fillRect.mockReset();
  context.drawImage.mockReset();
  context.save.mockReset();
  context.restore.mockReset();
  context.translate.mockReset();
  context.rotate.mockReset();
  relayTrack.contentHint = "";
  relayTrack.stop.mockReset();
  relayStream.getVideoTracks.mockClear();
  relayStream.getTracks.mockClear();

  originalCaptureStream = Object.getOwnPropertyDescriptor(
    HTMLCanvasElement.prototype,
    "captureStream",
  );
  captureStream = vi.fn(() => relayStream);
  Object.defineProperty(HTMLCanvasElement.prototype, "captureStream", {
    configurable: true,
    value: captureStream,
  });
  getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    context as unknown as CanvasRenderingContext2D,
  );

  vi.stubGlobal("RTCPeerConnection", FakePeerConnection);
  vi.stubGlobal("RTCRtpTransceiver", FakeTransceiver);
  vi.stubGlobal("RTCRtpSender", {
    getCapabilities: vi.fn(() => ({
      codecs: [
        { mimeType: "video/VP8", clockRate: 90_000, preferredPayloadType: 96 },
        {
          mimeType: "video/H264",
          clockRate: 90_000,
          preferredPayloadType: 102,
          sdpFmtpLine: "profile-level-id=42e01f;packetization-mode=1",
        },
        {
          mimeType: "video/rtx",
          clockRate: 90_000,
          preferredPayloadType: 103,
          sdpFmtpLine: "apt=102",
        },
      ],
      headerExtensions: [],
    })),
  });
  vi.stubGlobal("fetch", successfulFetch());
});

afterEach(() => {
  getContext.mockRestore();
  if (originalCaptureStream) {
    Object.defineProperty(
      HTMLCanvasElement.prototype,
      "captureStream",
      originalCaptureStream,
    );
  } else {
    delete (HTMLCanvasElement.prototype as unknown as Record<string, unknown>).captureStream;
  }
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("containRect", () => {
  it("fills an output with a matching 16:9 source", () => {
    expect(containRect(1280, 720, 1280, 720)).toEqual({
      x: 0,
      y: 0,
      width: 1280,
      height: 720,
    });
  });

  it("centres portrait and square sources with pillarboxing", () => {
    expect(containRect(720, 1280, 1280, 720)).toEqual({
      x: 437.5,
      y: 0,
      width: 405,
      height: 720,
    });
    expect(containRect(1000, 1000, 1280, 720)).toEqual({
      x: 280,
      y: 0,
      width: 720,
      height: 720,
    });
  });

  it("centres an ultrawide source with letterboxing", () => {
    expect(containRect(2560, 1080, 1280, 720)).toEqual({
      x: 0,
      y: 90,
      width: 1280,
      height: 540,
    });
  });

  it("rejects invalid dimensions", () => {
    expect(() => containRect(0, 720, 1280, 720)).toThrow(RangeError);
    expect(() => containRect(1280, Number.NaN, 1280, 720)).toThrow(RangeError);
  });
});

describe("MediaMTX endpoint configuration", () => {
  it("builds the LAN endpoints from a validated host", () => {
    expect(getMediaMtxEndpoints(" 192.168.0.106 ")).toEqual({
      host: "192.168.0.106",
      whipUrl: "http://192.168.0.106:8889/mimicmotion/whip",
      whepUrl: "http://192.168.0.106:8889/mimicmotion/",
      rtspUrl: "rtsp://192.168.0.106:8554/mimicmotion",
    });
  });

  it("rejects schemes, paths, ports, credentials, and invalid IPv4", () => {
    expect(getMediaMtxEndpoints(undefined)).toBeNull();
    expect(getMediaMtxEndpoints("http://192.168.0.106")).toBeNull();
    expect(getMediaMtxEndpoints("192.168.0.106:8889")).toBeNull();
    expect(getMediaMtxEndpoints("host/path")).toBeNull();
    expect(getMediaMtxEndpoints("user@host")).toBeNull();
    expect(getMediaMtxEndpoints("192.168.0.999")).toBeNull();
  });
});

describe("VideoWhipPublisher", () => {
  it("validates processed output readiness before allocating WebRTC", async () => {
    const video = createReadyVideo();
    Object.defineProperty(video, "readyState", { configurable: true, value: 0 });
    const statuses: BroadcastStatus[] = [];
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
      onStatusChange: (status) => statuses.push(status),
    });

    await expect(publisher.start()).rejects.toThrow("has not decoded");
    expect(FakePeerConnection.instances).toHaveLength(0);
    expect(statuses).toEqual(["connecting", "error"]);
  });

  it("draws the initial contained frame and publishes only H.264 video", async () => {
    const video = createReadyVideo();
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
      rotation: 0,
    });

    await publisher.start();

    const peerConnection = FakePeerConnection.instances[0];
    expect(context.drawImage).toHaveBeenCalledWith(video, 437.5, 0, 405, 720);
    expect(captureStream).toHaveBeenCalledWith(30);
    expect(relayTrack.contentHint).toBe("motion");
    expect(peerConnection.addTransceiver).toHaveBeenCalledOnce();
    expect(peerConnection.addTransceiver).toHaveBeenCalledWith(relayTrack, {
      direction: "sendonly",
      streams: [relayStream],
    });
    expect(peerConnection.transceiver.setCodecPreferencesMock).toHaveBeenCalledWith([
      expect.objectContaining({ mimeType: "video/H264" }),
      expect.objectContaining({ mimeType: "video/rtx", sdpFmtpLine: "apt=102" }),
    ]);
    expect(peerConnection.setRemoteDescription).toHaveBeenCalledWith({
      type: "answer",
      sdp: [
        "v=0",
        "a=rtcp-mux",
        "a=candidate:123 1 udp 2130706431 192.168.0.106 8189 typ host",
      ].join("\r\n") + "\r\n",
    });

    const fetchMock = vi.mocked(fetch);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://192.168.0.106:8889/mimicmotion/whip",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: "v=0\r\n",
      }),
    );
  });

  it("rotates the relay canvas 90 degrees by default", async () => {
    const video = createReadyVideo(720, 1280);
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
    });

    await publisher.start();

    // 90° is the default. For 720×1280 source, logical size is 1280×720 so the
    // 1280×720 output is filled exactly: rect = {0,0,1280,720}. The draw is via
    // translate(640,360) + rotate(π/2) + drawImage centred at (-640, -360).
    expect(publisher.getRotation()).toBe(90);
    expect(context.save).toHaveBeenCalledOnce();
    expect(context.translate).toHaveBeenCalledWith(640, 360);
    expect(context.rotate).toHaveBeenCalledWith(Math.PI / 2);
    expect(context.drawImage).toHaveBeenCalledWith(video, -640, -360, 1280, 720);
    expect(context.restore).toHaveBeenCalledOnce();
  });

  it("applies a mid-broadcast rotation change to the next drawn frame", async () => {
    const video = createReadyVideo(720, 1280);
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
    });
    await publisher.start();
    context.drawImage.mockClear();
    context.rotate.mockClear();

    publisher.setRotation(270);

    expect(publisher.getRotation()).toBe(270);
    expect(context.rotate).toHaveBeenCalledWith(-Math.PI / 2);
    expect(context.drawImage).toHaveBeenCalledWith(video, -640, -360, 1280, 720);

    context.drawImage.mockClear();
    publisher.setRotation(270);
    expect(context.drawImage).not.toHaveBeenCalled();
  });

  it("stops and deletes the resolved WHIP resource idempotently", async () => {
    const video = createReadyVideo();
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
    });
    await publisher.start();
    const peerConnection = FakePeerConnection.instances[0];

    await publisher.stop();
    await publisher.stop();

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenLastCalledWith(
      "http://192.168.0.106:8889/mimicmotion/whip/session-id",
      { method: "DELETE" },
    );
    expect(peerConnection.close).toHaveBeenCalledOnce();
    expect(relayTrack.stop).toHaveBeenCalledOnce();
    expect(video.cancelVideoFrameCallback).toHaveBeenCalledOnce();
    expect(publisher.getStatus()).toBe("idle");
  });

  it("cancels an in-flight start without allowing a stale live state", async () => {
    const statuses: BroadcastStatus[] = [];
    const video = createReadyVideo();
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
      onStatusChange: (status) => statuses.push(status),
    });
    FakePeerConnection.initialIceGatheringState = "new";

    const starting = publisher.start();
    await Promise.resolve();
    await publisher.stop();
    await starting;

    expect(statuses).toEqual(["connecting", "stopping", "idle"]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("releases local resources when WHIP signaling is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network error")));
    const video = createReadyVideo();
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
    });

    await expect(publisher.start()).rejects.toThrow("Could not reach MediaMTX");
    expect(FakePeerConnection.instances[0].close).toHaveBeenCalledOnce();
    expect(relayTrack.stop).toHaveBeenCalledOnce();
    expect(video.cancelVideoFrameCallback).toHaveBeenCalledOnce();
    expect(publisher.getStatus()).toBe("error");
  });

  it("reports and cleans up a connection failure after going live", async () => {
    const statuses: BroadcastStatus[] = [];
    const video = createReadyVideo();
    const publisher = new VideoWhipPublisher(video, {
      endpoint: "http://192.168.0.106:8889/mimicmotion/whip",
      onStatusChange: (status) => statuses.push(status),
    });
    await publisher.start();
    const peerConnection = FakePeerConnection.instances[0];

    peerConnection.connectionState = "failed";
    peerConnection.dispatchEvent(new Event("connectionstatechange"));

    await vi.waitFor(() => expect(publisher.getStatus()).toBe("error"));
    expect(statuses).toEqual(["connecting", "live", "error"]);
    expect(peerConnection.close).toHaveBeenCalledOnce();
    expect(relayTrack.stop).toHaveBeenCalledOnce();
  });
});
