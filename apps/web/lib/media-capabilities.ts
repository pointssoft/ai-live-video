export interface RecordingFormat {
  recorderMimeType: string;
  uploadContentType: "video/webm" | "video/mp4";
}

const candidates: RecordingFormat[] = [
  { recorderMimeType: "video/webm;codecs=vp9", uploadContentType: "video/webm" },
  { recorderMimeType: "video/webm;codecs=vp8", uploadContentType: "video/webm" },
  { recorderMimeType: "video/mp4;codecs=avc1.42E01E", uploadContentType: "video/mp4" },
];

export function selectRecordingFormat(): RecordingFormat | null {
  if (typeof MediaRecorder === "undefined") return null;
  return candidates.find(({ recorderMimeType }) => MediaRecorder.isTypeSupported(recorderMimeType)) ?? null;
}
