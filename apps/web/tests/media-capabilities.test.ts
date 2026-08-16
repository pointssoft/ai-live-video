import { afterEach, describe, expect, it, vi } from "vitest";
import { selectRecordingFormat } from "@/lib/media-capabilities";

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
