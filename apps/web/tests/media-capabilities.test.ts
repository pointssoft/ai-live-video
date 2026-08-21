import { afterEach, describe, expect, it, vi } from "vitest";
import { selectRecordingFormat } from "@/lib/media-capabilities";
import { recordingCrop } from "@/hooks/useMediaRecorder";

describe("recording format selection", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("prefers VP9 WebM and returns a bare upload MIME", () => {
    vi.stubGlobal("MediaRecorder", { isTypeSupported: (type: string) => type.includes("vp9") });
    expect(selectRecordingFormat()).toEqual({ recorderMimeType: "video/webm;codecs=vp9", uploadContentType: "video/webm" });
  });
  it("returns null without MediaRecorder", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    expect(selectRecordingFormat()).toBeNull();
  });
});

describe("portrait-matched recording crop", () => {
  it("center-crops a landscape camera to a portrait ratio", () => {
    expect(recordingCrop(1280, 720, 3 / 4)).toEqual({
      sourceX: 370,
      sourceY: 0,
      sourceWidth: 540,
      sourceHeight: 720,
      outputWidth: 540,
      outputHeight: 720,
    });
  });

  it("center-crops camera height when the portrait is wider", () => {
    expect(recordingCrop(1280, 720, 2)).toEqual({
      sourceX: 0,
      sourceY: 40,
      sourceWidth: 1280,
      sourceHeight: 640,
      outputWidth: 1280,
      outputHeight: 640,
    });
  });
});
