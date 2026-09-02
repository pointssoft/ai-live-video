# MimicMotion Realtime Output → RTSP LAN Broadcast Plan

## Objective

`apps/web/components/realtime/RealtimeStudio.tsx`-এ LiveKit realtime worker থেকে আসা **processed portrait output** local network-এ RTSP stream হিসেবে broadcast করা হবে। এটি camera preview নয়; broadcast source হবে `outputVideoRef`-এ attach হওয়া remote processed video track।

```text
Camera
  → LiveKit participant track
  → MimicMotion realtime worker / LivePortrait
  → LiveKit remote processed video track
  → RealtimeStudio outputVideoRef
  → hidden 1280×720 relay canvas
  → H.264 WebRTC / WHIP
  → local MediaMTX
  → RTSP over TCP
  → VLC / OBS / Android RTSP client
```

Default endpoints:

```text
WHIP publish: http://<LAN_IP>:8889/mimicmotion/whip
WHEP viewer:  http://<LAN_IP>:8889/mimicmotion/
RTSP output:  rtsp://<LAN_IP>:8554/mimicmotion
```

Default media profile:

| Field | Value |
| --- | --- |
| Source | LiveKit processed output video |
| Output resolution | 1280×720 |
| Maximum frame rate | 30 fps |
| Codec | H.264 |
| Audio | None |
| Scaling | Contain + centred letterbox |
| RTSP transport | TCP |
| Active publisher limit | One publisher on `mimicmotion` path |

---

## Why the LensCard implementation must be adapted

LensCard XR publishes a WebGL canvas. `RealtimeStudio.tsx` does not render its final output to a canvas. Its final output is a LiveKit `RemoteTrack` attached to:

```ts
const outputVideoRef = useRef<HTMLVideoElement>(null);
```

Therefore the optimized MimicMotion path is:

```text
HTMLVideoElement → relay canvas → captureStream(30) → WHIP
```

Do **not**:

- broadcast `localVideoRef`; that is the raw camera preview;
- publish `cameraTrackRef`; that is the input sent to LivePortrait;
- add WebGL `preserveDrawingBuffer`; this project’s source is a decoded `<video>`, not a WebGL canvas;
- add RTSP logic to the Python realtime worker or FastAPI API—the browser already receives the final processed frame, and the requested RTSP endpoint is a local-LAN concern;
- replace the existing LiveKit session or read-only viewer-token feature.

The relay canvas is intentionally retained even though the source is a video. It provides a predictable 1280×720 stream, normalizes portrait-dependent output dimensions, guarantees video-only output, and lets the browser negotiate a known H.264 sender for MediaMTX.

---

## Scope

### Included

- Manual **Start Broadcast** / **Stop Broadcast** controls in the live sidebar.
- Broadcast only after the processed output has a decoded frame.
- Fixed 1280×720 relay canvas with non-distorting letterboxing.
- H.264-only WHIP publication to local MediaMTX.
- RTSP and WHEP playback from MediaMTX.
- Separate broadcast status/error state from the existing LiveKit session state.
- Automatic broadcast cleanup when:
  - the user stops broadcasting;
  - the realtime session stops;
  - the remote output track is unsubscribed;
  - LiveKit disconnects;
  - `RealtimeStudio` unmounts or Next Fast Refresh replaces it;
  - WHIP/WebRTC fails.
- Unit tests for frame layout and publisher lifecycle.
- Browser/WHEP/RTSP verification.
- LAN-only Docker and firewall documentation.

### Not included

- Audio or microphone forwarding.
- Replacing LiveKit’s existing read-only viewer flow.
- Server-side transcoding.
- Internet-facing MediaMTX deployment.
- Automatic broadcast immediately when LiveKit becomes live.
- More than one publisher on the same RTSP path.
- Recording or playback history.

---

## Target files

### New MimicMotion files

```text
apps/web/lib/video-whip-publisher.ts
apps/web/tests/video-whip-publisher.test.ts
STREAMING_REALTIME.md
```

### Existing files to update

```text
apps/web/components/realtime/RealtimeStudio.tsx
apps/web/app/globals.css
apps/web/.env.example
D:\virtual-cam-laptop\LensCardXR\mediamtx.yml  # shared running server config
```

### Files intentionally unchanged

```text
realtime_worker/main.py
realtime_worker/liveportrait.py
apps/api/app/api/v1/realtime_sessions.py
docker/compose.local.yaml
D:\virtual-cam-laptop\LensCardXR\compose.yml
D:\virtual-cam-laptop\LensCardXR\.env
```

`docker/compose.local.yaml` remains MimicMotion’s existing PostgreSQL/MinIO/media-validator stack. No second MediaMTX service is added there. MimicMotion reuses the already running `lenscardxr-mediamtx-1` container owned by `D:\virtual-cam-laptop\LensCardXR\compose.yml`; only that server’s mounted path configuration is extended.

---

# Implementation

## Phase 1 — Add explicit browser-safe streaming configuration

Update `apps/web/.env.example`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Optional LAN-only MediaMTX host. The Broadcast UI is unavailable when omitted.
NEXT_PUBLIC_MEDIAMTX_HOST=192.168.1.100
```

Configuration rules:

1. `NEXT_PUBLIC_MEDIAMTX_HOST` contains only a hostname or IPv4 address—no scheme, path, or credentials.
2. Trim and validate it before building endpoint URLs.
3. Do not silently use a production Railway hostname as the MediaMTX host.
4. If the variable is missing, render Broadcast as “Not configured” or omit the controls rather than targeting an accidental host.
5. Build these URLs client-side:

```ts
const whipUrl = `http://${mediaMtxHost}:8889/mimicmotion/whip`;
const whepUrl = `http://${mediaMtxHost}:8889/mimicmotion/`;
const rtspUrl = `rtsp://${mediaMtxHost}:8554/mimicmotion`;
```

This is safe as a `NEXT_PUBLIC_*` setting because it is only a LAN address, not a secret. Never put MediaMTX credentials in a public environment variable if authentication is added later.

For the current running container, use its advertised LAN IP `192.168.0.106` in `apps/web/.env`, then restart the Next dev server because public environment values are loaded at startup/build time. If the host IP changes later, update both the LensCardXR MediaMTX environment and MimicMotion’s public host value together.

---

## Phase 2 — Implement `VideoWhipPublisher`

Create `apps/web/lib/video-whip-publisher.ts` as a framework-independent browser module.

### Public contract

```ts
export type BroadcastStatus =
  | "idle"
  | "connecting"
  | "live"
  | "stopping"
  | "error";

export interface VideoWhipPublisherOptions {
  endpoint: string;
  width?: number;
  height?: number;
  frameRate?: number;
  backgroundColor?: string;
  connectionTimeoutMs?: number;
  onStatusChange?: (status: BroadcastStatus, error?: Error) => void;
}

export class VideoWhipPublisher {
  constructor(
    sourceVideo: HTMLVideoElement,
    options: VideoWhipPublisherOptions,
  );

  getStatus(): BroadcastStatus;
  start(): Promise<void>;
  stop(): Promise<void>;
}
```

### 2.1 Browser support and source readiness

Before allocating WebRTC resources, require:

- `RTCPeerConnection`;
- `HTMLCanvasElement.captureStream`;
- `RTCRtpSender.getCapabilities("video")`;
- `RTCRtpTransceiver.setCodecPreferences`;
- `sourceVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA`;
- `sourceVideo.videoWidth > 0` and `sourceVideo.videoHeight > 0`.

Return distinct actionable errors for:

- processed output not ready;
- canvas capture unsupported;
- H.264 encoder unavailable;
- MediaMTX signaling unreachable;
- ICE/media connection timeout;
- MediaMTX rejecting the WHIP request.

### 2.2 Relay canvas and aspect handling

Create an in-memory canvas at exactly 1280×720 with a 2D context using `{ alpha: false }`.

For every source frame:

1. fill the entire output black;
2. read the current `videoWidth` and `videoHeight` because portrait changes may alter source geometry;
3. calculate `contain` dimensions;
4. draw the source centred without stretching or cropping.

```ts
const scale = Math.min(
  outputWidth / sourceWidth,
  outputHeight / sourceHeight,
);
const width = sourceWidth * scale;
const height = sourceHeight * scale;
const x = (outputWidth - width) / 2;
const y = (outputHeight - height) / 2;
```

Export the pure geometry helper (for example `containRect`) so it can be unit tested without canvas APIs.

The UI uses `object-fit: contain`; the RTSP output should preserve the same visual intent.

### 2.3 Video-driven frame copying

Use `HTMLVideoElement.requestVideoFrameCallback()` when available. This is more efficient for MimicMotion than a free-running render loop because it copies only when LiveKit delivers a decoded processed frame.

Requirements:

- draw one valid initial frame before attaching the captured track to WebRTC;
- schedule the next callback after each callback;
- cap copies at the configured 30 fps if decoded callbacks arrive faster;
- use `requestAnimationFrame` only as a compatibility fallback;
- retain callback IDs and cancel them during cleanup;
- re-read source dimensions on every accepted frame;
- optionally toggle a 1–2 px edge heartbeat on each copied frame so nearly static portrait output still produces observable canvas changes;
- use `relayCanvas.captureStream(30)`, not `captureStream(0)` plus manual `requestFrame()`;
- set `videoTrack.contentHint = "motion"`.

`captureStream(30)` is a maximum capture rate. If the realtime worker outputs fewer decoded frames, the publisher should not invent motion or duplicate frames merely to claim 30 fps.

### 2.4 H.264-only sender

1. Create `RTCPeerConnection`.
2. Add the relay video track with a send-only transceiver.
3. Filter `RTCRtpSender.getCapabilities("video")?.codecs` to MIME type `video/H264`.
4. Preserve all browser H.264 variants returned, including RTX associations where required by browser behavior.
5. Call `transceiver.setCodecPreferences(...)` before creating the offer.
6. Fail clearly if no usable H.264 codec exists.

No audio track is created. Do not use `outputVideo.srcObject` wholesale because it may later gain audio; capture only the relay canvas video track.

### 2.5 WHIP signaling

Use a complete non-trickle ICE exchange:

1. create offer;
2. set local description;
3. wait for ICE gathering state `complete`;
4. `POST` SDP to `/mimicmotion/whip` with `Content-Type: application/sdp`;
5. require a successful response;
6. save the WHIP resource URL from `Location`, resolved relative to the endpoint;
7. read the SDP answer;
8. remove only a terminal `a=end-of-candidates` line if Chromium rejects that MediaMTX answer form;
9. set remote description;
10. wait for `connectionState === "connected"`;
11. then emit `live`.

ICE connected by itself is not proof of working video. Runtime verification must also inspect outbound RTP bytes, packets, and frames.

### 2.6 Idempotency and stale-operation protection

Use an incrementing operation token:

- `start()` while connecting/live is a no-op;
- repeated `stop()` is safe;
- Stop invalidates an in-flight Start;
- stale fetch/ICE completion cannot set the publisher back to `live`;
- an `AbortController` cancels the WHIP request;
- peer-connection failure after Live releases resources and emits `error`.

### 2.7 Cleanup order

On Stop/failure:

1. abort pending fetch;
2. send `DELETE` to the WHIP resource URL, if present;
3. remove peer-connection listeners;
4. close the peer connection;
5. cancel `requestVideoFrameCallback` or RAF fallback;
6. stop every relay `MediaStreamTrack`;
7. clear references to relay canvas/context/stream/resource URL.

WHIP DELETE failure is non-fatal; local connection closure still ends publishing and MediaMTX expires the disconnected session.

---

## Phase 3 — Integrate into `RealtimeStudio.tsx`

## 3.1 Add state and refs

Keep broadcast state fully separate from existing LiveKit `status` and `error`:

```ts
const [broadcastStatus, setBroadcastStatus] =
  useState<BroadcastStatus>("idle");
const [broadcastError, setBroadcastError] = useState("");
const [rtspCopied, setRtspCopied] = useState(false);
const [outputReady, setOutputReady] = useState(false);
const publisherRef = useRef<VideoWhipPublisher | null>(null);
```

Why separate state matters:

- a MediaMTX failure must not end a healthy LiveKit session;
- an expression-control failure must not be presented as an RTSP failure;
- “Live” currently means LiveKit output exists, while broadcast `live` means MediaMTX publication is connected.

Do not overload the existing `status === "Live"` string with broadcast state.

## 3.2 Track decoded output readiness

Update both rendered processed-output `<video>` elements with readiness callbacks, especially the fullscreen one:

```tsx
<video
  ref={outputVideoRef}
  autoPlay
  playsInline
  onLoadedData={() => setOutputReady(true)}
  onEmptied={() => setOutputReady(false)}
  className="main-live-video"
/>
```

Because `RealtimeStudio` conditionally replaces the setup-layout video with the fullscreen-layout video, retain the existing `[isLive]` reattachment effect. The Start Broadcast action must also re-check the current DOM element’s `readyState`, `videoWidth`, and `videoHeight`; state alone is not enough.

## 3.3 Start Broadcast callback

`startBroadcast` should:

1. require configured MediaMTX host;
2. require `isLive`, `outputTrackRef.current`, `outputReady`, and current `outputVideoRef`;
3. stop any stale publisher instance first;
4. clear broadcast errors/copy confirmation;
5. instantiate `VideoWhipPublisher(outputVideoRef.current, ...)` with 1280×720 @ 30 fps;
6. assign it to `publisherRef` before awaiting Start;
7. ignore callback state from an instance that is no longer current;
8. report publisher errors only in `broadcastError`.

Do not stop the LiveKit room if WHIP publication fails.

## 3.4 Stop Broadcast callback

`stopBroadcast` should:

- retain the current publisher locally;
- await its idempotent `stop()`;
- clear `publisherRef` only if it still points to that publisher;
- reset copy state;
- leave the LiveKit room and processed video running.

## 3.5 Couple broadcast teardown to session teardown

Update the existing `stop()` callback to call `await stopBroadcast()` **before** it disconnects the room, clears `outputVideoRef.srcObject`, and nulls `outputTrackRef`.

This preserves the current Stop Session behavior while guaranteeing that one click stops both systems in the correct order:

```text
WHIP publisher → LiveKit camera/output tracks → room → realtime pod
```

The existing unmount cleanup (`useEffect(() => () => { void stop(); }, [stop])`) will then cover both systems. Publisher cleanup must remain idempotent because React Strict Mode and Fast Refresh can exercise teardown more than once.

## 3.6 Handle LiveKit track loss

Current Start and reconnect flows duplicate `TrackSubscribed` and `Disconnected` listeners. Before adding more lifecycle behavior, extract their common listener registration into one component callback/helper, for example `registerRoomListeners(room)`.

The shared listener setup should handle:

- `RoomEvent.TrackSubscribed`:
  - retain and attach a video output track;
  - clear worker timeout;
  - set LiveKit status to `Live`;
  - synchronize expression controls.
- `RoomEvent.TrackUnsubscribed`:
  - only act when it is the current `outputTrackRef`;
  - clear output track and `outputReady`;
  - stop the RTSP broadcast;
  - report that processed output is unavailable.
- `RoomEvent.Disconnected`:
  - clear worker timeout and stored session;
  - clear output readiness;
  - stop broadcast;
  - set existing session status to `Disconnected.`.

Use `RemoteVideoTrack` typing after checking `track.kind === Track.Kind.Video` if LiveKit types permit it. Avoid leaving `outputTrackRef` typed so broadly that video-only methods need unchecked casts.

Portrait changes do not stop broadcast. The relay recalculates geometry as processed frames continue.

## 3.7 Sidebar UI placement

Add a new `.broadcast-controls` block in the fullscreen `.live-sidebar`, after expression controls and before read-only viewer credentials.

It should show:

- heading: `LAN RTSP Broadcast`;
- independent status badge: Idle / Connecting / Live / Stopping / Error;
- Start Broadcast or Stop Broadcast button;
- RTSP URL in a read-only/wrapping field;
- Copy RTSP URL action;
- optional WHEP viewer link for diagnostics;
- inline `role="alert"` broadcast error.

Button rules:

- Start enabled only when:
  - MediaMTX host is configured;
  - LiveKit session status is Live;
  - processed output has a decoded frame;
  - publisher is not connecting/stopping/live.
- Stop enabled while connecting/live/error with an owned publisher.
- Session reconnecting disables Start.
- Stop Session remains available according to its existing rules and also cleans the broadcast.

Do not show Start Broadcast in the pre-session layout: there is no processed source at that point.

The existing read-only LiveKit credentials and QR code remain unchanged. Clarify in UI/docs that RTSP is a separate anonymous trusted-LAN output and does not use that viewer token.

## 3.8 Copy behavior

Add `copyRtspUrl` using `navigator.clipboard.writeText(rtspUrl)` with:

- visible `Copied` confirmation;
- failure routed to `broadcastError`, not the main session error;
- URL text still selectable manually because Clipboard API may be restricted on an insecure LAN origin.

---

## Phase 4 — Add styles in `apps/web/app/globals.css`

Match the existing dark sidebar style rather than introducing a new design system.

Add narrowly scoped classes such as:

```text
.broadcast-controls
.broadcast-heading
.broadcast-status
.broadcast-status-dot
.broadcast-url
.broadcast-actions
.broadcast-error
```

Requirements:

- reuse existing `#2d3855`, `#0f1629`, `var(--surface)`, `var(--text)`, `var(--muted)`, and `var(--accent)` tokens;
- show status with text and color, not color alone;
- use green for Live and red for Error;
- preserve visible `:focus-visible` outlines;
- make long RTSP URLs wrap with `overflow-wrap: anywhere`;
- buttons fit the 360 px sidebar and narrow 40vw layout;
- disabled state is visually clear;
- do not alter `.main-live-video { object-fit: contain; }`;
- verify the sidebar remains scrollable with Broadcast + viewer credentials + QR code;
- preserve the camera preview at the bottom without making controls unreachable.

Consider reducing repeated inline UI by extracting only the Broadcast block to a small local component if `RealtimeStudio.tsx` becomes harder to scan. Do not move LiveKit ownership out of `RealtimeStudio` as part of this feature.

---

## Phase 5 — Reuse the running MediaMTX container

Do not create a MediaMTX service inside MimicMotion and do not start a second container. The required server is already running:

| Property | Current value |
| --- | --- |
| Container | `lenscardxr-mediamtx-1` |
| Compose owner | `D:\virtual-cam-laptop\LensCardXR\compose.yml` |
| Image | `bluenviron/mediamtx:latest` |
| Advertised WebRTC host | `192.168.0.106` |
| RTSP | host `8554/tcp` |
| WHIP/WHEP | host `8889/tcp` |
| WebRTC media | host `8189/udp` |
| Existing path | `lenscard` |

These ports are already bound, so a second server would fail with port conflicts. The shared container can publish `lenscard` and `mimicmotion` concurrently because they are separate paths.

## 5.1 Extend the mounted MediaMTX config

The running container mounts this host file read-only:

```text
D:\virtual-cam-laptop\LensCardXR\mediamtx.yml
```

Preserve all existing `lenscard` permissions and path configuration. Add equivalent permissions for `mimicmotion` to the same anonymous trusted-LAN user:

```yaml
authMethod: internal
authInternalUsers:
  - user: any
    pass:
    ips: []
    permissions:
      - action: publish
        path: lenscard
      - action: read
        path: lenscard
      - action: playback
        path: lenscard
      - action: publish
        path: mimicmotion
      - action: read
        path: mimicmotion
      - action: playback
        path: mimicmotion

paths:
  lenscard:
    source: publisher
    overridePublisher: false
  mimicmotion:
    source: publisher
    overridePublisher: false
```

Do not replace `lenscard` with `mimicmotion`; both paths must remain available. Retain the existing RTSP-over-TCP and WebRTC settings:

```yaml
rtspTransports: [tcp]
webrtcAddress: :8889
webrtcLocalUDPAddress: :8189
webrtcIPsFromInterfaces: false
```

No changes are required in MimicMotion’s `docker/compose.local.yaml`, LensCardXR’s `compose.yml`, or its `.env` while the current ports and LAN IP remain correct.

## 5.2 Validate before reloading

From `D:\virtual-cam-laptop\LensCardXR`, validate the existing Compose project after editing its MediaMTX config:

```bash
docker compose config
```

Confirm the running server and current port ownership:

```bash
docker compose ps mediamtx
```

The YAML mounted at `/mediamtx.yml` is read when MediaMTX starts. After the configuration edit, reload only this shared service:

```bash
docker compose restart mediamtx
```

A restart briefly interrupts any active `lenscard` publisher/viewer, so perform it once during setup—not every time MimicMotion starts. Do not run `docker compose down`, because that would also affect the LensCard XR Compose project’s other service(s).

Then inspect startup/config errors:

```bash
docker compose logs --tail 100 mediamtx
```

Expected result:

- the same `lenscardxr-mediamtx-1` service returns to Running;
- ports 8554, 8889, and 8189 remain unchanged;
- both `lenscard` and `mimicmotion` paths are authorized;
- no duplicate MediaMTX container exists.

## 5.3 Shared-server operating rule

MimicMotion owns only its browser publisher and the `mimicmotion` path. It must not start, stop, recreate, or remove the MediaMTX container during normal Start Broadcast / Stop Broadcast actions.

- **Start Broadcast** creates only a WHIP publishing session on `/mimicmotion/whip`.
- **Stop Broadcast** DELETEs/closes only that WHIP session.
- LensCard continues to use `/lenscard/whip` and `/lenscard` independently.
- One active publisher is allowed per path; one publisher on each of the two paths can coexist.
- Container lifecycle remains managed from the LensCardXR Compose directory.

The running image is currently `bluenviron/mediamtx:latest`. Reusing the existing container means this MimicMotion task must not silently change or repin that shared image. Version pinning, if desired, should be handled as a separate LensCardXR infrastructure change with compatibility verification for both publishers.

---

## Phase 6 — Tests

Create `apps/web/tests/video-whip-publisher.test.ts` using Vitest/jsdom with browser APIs stubbed.

### Pure layout tests

Test `containRect` for:

- 1280×720 source → fills 1280×720;
- 720×1280 portrait source → pillarboxed and centred;
- square source → pillarboxed and centred;
- ultrawide source → letterboxed and centred;
- zero/invalid source dimensions → rejected or skipped safely.

### Publisher tests

Mock/stub:

- canvas `getContext` and `captureStream`;
- `requestVideoFrameCallback` / cancellation;
- `RTCPeerConnection` and transceiver;
- `RTCRtpSender.getCapabilities`;
- `fetch` for WHIP POST/DELETE;
- fake video and media tracks.

Verify:

1. source readiness is validated before signaling;
2. only H.264 codecs are preferred;
3. no audio track is added;
4. WHIP POST uses `application/sdp`;
5. relative `Location` becomes a valid resource URL;
6. successful connection emits `connecting → live`;
7. Stop sends DELETE, closes peer connection, cancels frame callback, and stops track;
8. repeated Stop remains safe;
9. Stop during Start prevents stale `live` state;
10. network failure releases all allocated resources;
11. connection failure after Live emits `error`;
12. initial frame and contain rectangle are drawn correctly.

### `RealtimeStudio` integration tests

If adding a focused component test, mock LiveKit and `VideoWhipPublisher` to verify:

- Start Broadcast is unavailable before processed output readiness;
- publisher receives `outputVideoRef.current`, not `localVideoRef.current`;
- WHIP failure does not call Stop Session;
- Stop Session calls publisher Stop;
- remote track unsubscribe/disconnect stops the publisher;
- unmount stops the publisher;
- copy action uses the configured RTSP URL.

Do not attempt real LiveKit, WebRTC, canvas encoding, or MediaMTX networking in jsdom tests; those belong to browser integration verification.

---

## Phase 7 — Automated project verification

Follow the repository’s required web verification order from the repository root:

```bash
npx pnpm@10.15.0 --dir apps/web run lint
```

```bash
npx pnpm@10.15.0 --dir apps/web run typecheck
```

```bash
npx pnpm@10.15.0 --dir apps/web run test -- --run
```

```bash
npx pnpm@10.15.0 --dir apps/web run build
```

Focused test while developing:

```bash
npx pnpm@10.15.0 --dir apps/web run test -- --run tests/video-whip-publisher.test.ts
```

Also validate the existing shared MediaMTX Compose project from `D:\virtual-cam-laptop\LensCardXR`:

```bash
docker compose config
```

```bash
docker compose ps mediamtx
```

Do not start another MediaMTX container as part of MimicMotion verification.

No Python worker/API test is required if those files remain unchanged. If implementation unexpectedly changes realtime-worker or API contracts, run their repository-defined gates separately rather than mixing environments.

---

## Phase 8 — Real browser and media verification

Unit tests cannot prove browser H.264 encoding or MediaMTX interoperability.

### 8.1 Setup

1. Confirm `NEXT_PUBLIC_MEDIAMTX_HOST=192.168.0.106` in `apps/web/.env`; this matches the host currently advertised by `lenscardxr-mediamtx-1`.
2. Confirm the existing container is running with `docker compose ps mediamtx` from `D:\virtual-cam-laptop\LensCardXR`; do not start a second server.
3. After the one-time `mimicmotion` path configuration and shared-service restart, start the existing API and Next web development workflows.
4. Open the web app and establish a normal realtime portrait session.
5. Wait until processed output is visibly moving and Broadcast is enabled.

### 8.2 WHIP publisher verification

Press **Start Broadcast** and confirm:

- broadcast status transitions `Idle → Connecting → Live`;
- WHIP POST returns success, normally `201`;
- browser peer connection reaches `connected`;
- browser outbound RTP stats show increasing:
  - `bytesSent`;
  - `packetsSent`;
  - `framesEncoded`;
- encoded dimensions are 1280×720;
- only one outbound video sender exists and no audio sender exists;
- MediaMTX logs report one H.264 track published on `mimicmotion`.

ICE connection alone is insufficient. Nonzero media statistics are mandatory.

### 8.3 WHEP verification

Open the canonical trailing-slash URL:

```text
http://<LAN_IP>:8889/mimicmotion/
```

Confirm:

- video dimensions become 1280×720;
- `currentTime` advances;
- inbound bytes/packets and decoded frames increase;
- the frame is the processed portrait—not the raw mirrored camera;
- portrait aspect is preserved with black letterboxing when needed;
- expression and portrait changes are visible without restarting broadcast;
- there is no audio track.

### 8.4 RTSP verification

Open in VLC:

```text
rtsp://<LAN_IP>:8554/mimicmotion
```

Prefer RTSP-over-TCP. Confirm MediaMTX/VLC evidence for:

- OPTIONS `200`;
- DESCRIBE `200` with `H264/90000`;
- SETUP `200`;
- PLAY `200`;
- SPS/PPS received;
- H.264 decoder started;
- live processed frames displayed.

Alternative:

```bash
ffplay -rtsp_transport tcp rtsp://<LAN_IP>:8554/mimicmotion
```

### 8.5 Lifecycle verification

Exercise:

1. Start Broadcast → Stop Broadcast → Start Broadcast again.
2. Change portrait while broadcasting.
3. Change expression sliders while broadcasting.
4. Stop Session while broadcasting.
5. Simulate LiveKit disconnect/remote track unsubscribe.
6. Navigate away from `/live` while broadcasting.
7. Trigger Next Fast Refresh during development.
8. Try Start before `loadeddata`—it must remain disabled or show a readiness error.
9. Stop while WHIP is still connecting—no stale `live` state may appear.
10. Start an RTSP viewer before broadcasting—it should report no stream; the URL must not be changed as a workaround.

---

## Phase 9 — LAN firewall and security

Allow inbound traffic on the host’s active **Private** network profile:

| Port | Protocol | Purpose |
| --- | --- | --- |
| 3000 | TCP | Next.js app, only if opened from another LAN device |
| 8554 | TCP | RTSP playback |
| 8889 | TCP | WHIP/WHEP HTTP signaling |
| 8189 | UDP | WebRTC ICE/media |

API/LiveKit/storage ports are outside this feature and should not be opened merely for RTSP playback.

Security rules:

- limit firewall rules to the local subnet;
- verify Windows Wi-Fi/Ethernet is classified `Private`; Private-only rules do not apply on a Public profile;
- do not configure router port forwarding for 8554/8889/8189;
- treat RTSP output as an additional viewer channel that bypasses the existing LiveKit viewer token;
- keep broadcast manual and visibly indicated;
- for an untrusted/shared network, add MediaMTX authentication, restrict IP ranges/CORS, and use TLS before enabling it.

### HTTP/HTTPS constraint

The local plan assumes the Next page and MediaMTX WHIP endpoint are both HTTP. An HTTPS Railway page cannot publish to an HTTP LAN WHIP endpoint because browsers block mixed active content.

Therefore:

- local RTSP publishing is supported from the local HTTP Next deployment;
- production HTTPS support is a separate deployment design requiring trusted TLS for MediaMTX and an HTTPS WHIP endpoint;
- keep Broadcast unavailable in production when `NEXT_PUBLIC_MEDIAMTX_HOST` is not explicitly configured.

---

## Phase 10 — Documentation

Create `STREAMING_REALTIME.md` with:

1. architecture and explicit statement that the source is processed LivePortrait output;
2. `NEXT_PUBLIC_MEDIAMTX_HOST` setup using the shared server’s existing LAN IP;
3. the existing `lenscardxr-mediamtx-1` container name, LensCardXR Compose ownership, and config location;
4. one-time `mimicmotion` path addition, validation, restart, status, and log commands;
5. warning that restarting the shared service briefly interrupts LensCard XR streaming;
6. Next/API/realtime-session prerequisites;
7. Start Broadcast and Stop Broadcast instructions;
8. WHIP/WHEP/RTSP URLs;
9. VLC, ffplay, OBS, and Android examples;
10. firewall ports and Windows Private-profile requirement;
11. trusted-LAN/no-auth warning;
12. mixed-content limitation;
13. one-publisher-per-path limitation and two-path coexistence;
14. troubleshooting table.

Troubleshooting must distinguish:

| Symptom | Likely cause |
| --- | --- |
| Broadcast button disabled | LiveKit output has not delivered a decoded frame, or MediaMTX host is not configured |
| WHIP unreachable | MediaMTX container/TCP 8889/host value/CORS |
| Connecting timeout | wrong advertised LAN IP or blocked UDP 8189 |
| Connected but zero RTP | canvas capture/H.264 sender/frame-copy loop |
| WHEP black | video readiness or `drawImage` path—not WebGL buffer preservation |
| RTSP 404/no stream | browser publisher is not currently Live |
| WHEP works, phone cannot connect | Windows profile/firewall/AP isolation/routing |
| Raw camera appears | publisher was incorrectly wired to `localVideoRef` instead of `outputVideoRef` |
| Portrait is stretched | contain rectangle or source-dimension handling is wrong |
| LiveKit works but Broadcast errors | keep session running; troubleshoot MediaMTX independently |

---

# Acceptance criteria

Implementation is complete only when every applicable item passes:

- [ ] Broadcast source is `outputVideoRef` / processed LiveKit output.
- [ ] Raw camera preview is never sent to MediaMTX.
- [ ] Broadcast cannot start before the first processed frame is decoded.
- [ ] Output is video-only H.264 at fixed 1280×720.
- [ ] Frame rate is capped at 30 fps and follows decoded LiveKit output cadence.
- [ ] Portrait, landscape, and square outputs are centred without distortion or cropping.
- [ ] LiveKit session state and RTSP broadcast state are independent.
- [ ] WHIP failure does not terminate a healthy realtime session.
- [ ] Stop Broadcast leaves the realtime session running.
- [ ] Stop Session, track unsubscribe, disconnect, and unmount stop the publisher.
- [ ] Repeated Start/Stop and Stop-during-Connect leave no stale publisher.
- [ ] WHIP POST and resource DELETE work.
- [ ] Browser outbound RTP bytes/packets/frames increase.
- [ ] WHEP receives non-black 1280×720 processed frames.
- [ ] VLC/ffplay decodes `rtsp://<LAN_IP>:8554/mimicmotion` over TCP.
- [ ] A second LAN device can decode the stream.
- [ ] Portrait and expression changes remain visible during one continuous broadcast.
- [ ] No microphone permission is requested and no audio track exists.
- [ ] Existing LiveKit viewer credentials/QR workflow is unchanged.
- [ ] Existing local Postgres/MinIO Compose workflow is unchanged.
- [ ] MimicMotion reuses `lenscardxr-mediamtx-1`; no second MediaMTX container or duplicate port binding exists.
- [ ] Shared `mediamtx.yml` retains the `lenscard` path and adds the separate `mimicmotion` path with publish/read/playback permissions.
- [ ] Normal Start/Stop Broadcast actions do not control the shared container lifecycle.
- [ ] LensCard and MimicMotion can publish concurrently on their respective paths.
- [ ] Lint, typecheck, Vitest, Next production build, shared Compose config, and MediaMTX startup checks pass.
- [ ] LAN security and HTTPS limitations are documented.

---

# Recommended implementation order

1. Add `video-whip-publisher.ts` and unit tests.
2. Add streaming env parsing and endpoint construction.
3. Extend LensCardXR’s mounted `mediamtx.yml` with the `mimicmotion` path, validate it, and restart only the existing shared MediaMTX service once.
4. Confirm both `lenscard` and `mimicmotion` paths work on `lenscardxr-mediamtx-1` without starting another container.
5. Refactor duplicated LiveKit room listeners in `RealtimeStudio`.
6. Add independent broadcast state, callbacks, and cleanup coupling.
7. Add sidebar controls and CSS.
8. Run web verification gates.
9. Verify real LiveKit processed output through WHIP and WHEP.
10. Verify RTSP on the host, then on another LAN device.
11. Write operator documentation and complete the acceptance checklist.

This order isolates browser capture, shared MediaMTX configuration, LiveKit integration, and UI problems instead of debugging all four layers simultaneously. It also makes the one shared-container interruption explicit and keeps normal MimicMotion broadcast operations path-scoped.
