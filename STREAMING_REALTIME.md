# Realtime processed output streaming

MimicMotion can publish the processed LivePortrait output from a realtime session to the existing LAN MediaMTX server. The broadcast source is the remote processed video attached to `outputVideoRef`; it is not the raw camera preview.

```text
Camera
  -> LiveKit realtime worker / LivePortrait
  -> LiveKit remote processed track
  -> browser 1280x720 relay canvas
  -> H.264 WebRTC / WHIP
  -> MediaMTX
  -> RTSP over TCP or WHEP
```

The broadcast is video-only, capped at 30 fps, and letterboxed without stretching or cropping. No microphone permission or audio track is used.

## Shared MediaMTX server

MimicMotion reuses the MediaMTX service owned by the LensCardXR Compose project. Do not start a second MediaMTX container because the required ports are already bound.

| Setting | Value |
| --- | --- |
| Container | `lenscardxr-mediamtx-1` |
| Compose directory | `D:\virtual-cam-laptop\LensCardXR` |
| Mounted configuration | `D:\virtual-cam-laptop\LensCardXR\mediamtx.yml` |
| LAN IP | `192.168.0.106` |
| LensCard XR path | `lenscard` |
| MimicMotion path | `mimicmotion` |

The two paths are independent. LensCard XR and MimicMotion can each have one publisher at the same time. `overridePublisher: false` prevents a second publisher from replacing the active publisher on either path.

## One-time MediaMTX setup

The shared `mediamtx.yml` must retain the existing `lenscard` path and include publish, read, and playback permissions plus a publisher path for `mimicmotion`:

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

From `D:\virtual-cam-laptop\LensCardXR`, validate the Compose configuration and inspect the existing service:

```bash
docker compose config
```

```bash
docker compose ps mediamtx
```

After changing only the bind-mounted `mediamtx.yml`, restart MediaMTX once so it reads the updated file:

```bash
docker compose restart mediamtx
```

A restart does not apply Compose environment changes. If `LAN_IP` (and therefore `MTX_WEBRTCADDITIONALHOSTS`) changes in the LensCardXR `.env`, recreate only the MediaMTX service:

```bash
docker compose up -d --no-deps --force-recreate mediamtx
```

Confirm that the recreated container advertises the current LAN address:

```bash
docker compose exec mediamtx printenv MTX_WEBRTCADDITIONALHOSTS
```

Either operation briefly interrupts active LensCard XR publishers and viewers. Do not run `docker compose down`.

Inspect startup and configuration errors:

```bash
docker compose logs --tail 100 mediamtx
```

Normal MimicMotion Start Broadcast and Stop Broadcast actions create and delete only a WHIP session on the `mimicmotion` path. They never control the shared container lifecycle.

## Web configuration

Set the LAN host in `apps/web/.env`:

```dotenv
NEXT_PUBLIC_MEDIAMTX_HOST=192.168.0.106
```

Use only a hostname or IPv4 address—no scheme, port, path, or credentials. Restart the Next.js development server after changing this value because `NEXT_PUBLIC_*` values are loaded at startup/build time. When the variable is omitted or invalid, the Broadcast panel displays **Not configured** and publication is unavailable.

Do not put MediaMTX credentials in a `NEXT_PUBLIC_*` variable. These values are included in browser JavaScript.

## Prerequisites and operation

1. Confirm `lenscardxr-mediamtx-1` is running.
2. Start the existing MimicMotion API and Next.js development workflows.
3. Open the local HTTP web app and start a realtime portrait session.
4. Wait until the processed portrait is visibly moving and the **Start Broadcast** button is enabled.
5. Select **Start Broadcast**. Its status should change from Idle to Connecting to Live.
6. Select **Stop Broadcast** to stop RTSP output while leaving the LiveKit realtime session running.
7. **Stop Session**, output-track loss, LiveKit disconnect, navigation, unmount, and Fast Refresh also clean up the publisher.

Changing the portrait or expression controls does not require restarting the broadcast.

## Endpoints

```text
WHIP publish: http://192.168.0.106:8889/mimicmotion/whip
WHEP viewer:  http://192.168.0.106:8889/mimicmotion/
RTSP output:  rtsp://192.168.0.106:8554/mimicmotion
```

The WHEP URL must keep its trailing slash.

### VLC

Open this network stream and select RTSP-over-TCP if VLC does not choose it automatically:

```text
rtsp://192.168.0.106:8554/mimicmotion
```

### ffplay

```bash
ffplay -rtsp_transport tcp rtsp://192.168.0.106:8554/mimicmotion
```

### OBS Studio

Add a **Media Source**, disable **Local File**, and use:

```text
rtsp://192.168.0.106:8554/mimicmotion
```

Set the RTSP input transport to TCP when the platform/plugin exposes that option.

### Android

Use an RTSP-capable player such as VLC for Android while the phone is connected to the same LAN. Open:

```text
rtsp://192.168.0.106:8554/mimicmotion
```

Some access points enable client/AP isolation and prevent Wi-Fi devices from reaching one another. Disable isolation or use a network where local clients can communicate.

## Verification

A successful WHIP request and connected ICE state do not by themselves prove that video is flowing.

In browser WebRTC diagnostics, confirm one outbound video sender, no audio sender, 1280x720 encoded dimensions, and increasing `bytesSent`, `packetsSent`, and `framesEncoded`.

In the WHEP viewer, confirm:

- dimensions become 1280x720;
- playback time and inbound bytes advance;
- the processed portrait appears instead of the mirrored raw camera;
- portrait/square sources retain their aspect ratio with black side bars;
- portrait and expression changes remain visible;
- no audio track exists.

For RTSP, MediaMTX/player diagnostics should show successful OPTIONS, DESCRIBE, SETUP, and PLAY requests, an `H264/90000` track, SPS/PPS, and decoded live frames.

## Windows firewall and LAN security

Allow inbound access only on the active **Private** network profile and, where possible, only from the local subnet:

| Port | Protocol | Purpose |
| --- | --- | --- |
| 3000 | TCP | Next.js, only when another LAN device opens the web app |
| 8554 | TCP | RTSP playback |
| 8889 | TCP | WHIP/WHEP HTTP signaling |
| 8189 | UDP | WebRTC ICE/media |

Do not open API, LiveKit, database, or storage ports merely for RTSP playback. Do not configure router port forwarding for ports 8554, 8889, or 8189.

The current MediaMTX paths are anonymous and intended only for a trusted LAN. RTSP is an additional viewer channel and bypasses the LiveKit read-only viewer token. On an untrusted/shared network, configure MediaMTX authentication, restrict client IP ranges and CORS, and use TLS before enabling broadcast.

## HTTP/HTTPS limitation

This setup assumes that both the local Next.js page and MediaMTX WHIP endpoint use HTTP. An HTTPS production page cannot publish to an HTTP LAN WHIP endpoint because browsers block mixed active content.

Production HTTPS broadcasting requires trusted TLS for MediaMTX and an HTTPS WHIP endpoint. Leave `NEXT_PUBLIC_MEDIAMTX_HOST` unset in production until that deployment is designed.

## Troubleshooting

| Symptom | Likely cause and action |
| --- | --- |
| Broadcast button disabled | Wait for LiveKit processed output to decode its first frame; also confirm `NEXT_PUBLIC_MEDIAMTX_HOST` is configured and restart Next.js after changing it. |
| Panel says Not configured | The public host variable is missing or contains a scheme, port, path, credentials, or invalid address. |
| WHIP unreachable | Check the MediaMTX container, LAN host, TCP 8889, CORS, and Windows Firewall. |
| Connecting timeout | Confirm MediaMTX advertises `192.168.0.106` and UDP 8189 is reachable. |
| Connected but RTP counters stay at zero | Inspect H.264 negotiation, canvas capture, and the video-frame copy loop. |
| WHEP is black | Confirm the processed `<video>` has decoded dimensions and `drawImage` is receiving frames. WebGL buffer preservation is not relevant. |
| RTSP reports 404/no stream | The browser publisher is not currently Live; keep the same RTSP URL and start Broadcast. |
| WHEP works but a phone cannot connect | Check Windows network profile/firewall, routing, and Wi-Fi client/AP isolation. |
| Raw camera appears | The publisher was wired incorrectly; it must use `outputVideoRef`, never `localVideoRef` or the camera track. |
| Portrait is stretched or cropped | Inspect contain-layout calculations and current source dimensions. |
| LiveKit works but Broadcast errors | Keep the realtime session running and troubleshoot MediaMTX independently. |
| Start fails with H.264 unavailable | Use a browser/platform that exposes an H.264 WebRTC encoder and codec preferences. |
| A second publisher is rejected | Stop the current publisher on `mimicmotion`; only one active publisher is allowed per path. |
