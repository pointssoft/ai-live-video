# Business Logic Specification

## 1. ডকুমেন্টের উদ্দেশ্য

এই ডকুমেন্টে MimicMotion-ভিত্তিক web application-এর product rules, user journey, domain model, generation lifecycle, validation, retry, retention, quota এবং acceptance criteria নির্ধারণ করা হয়েছে। এটি product, frontend, backend, ML, QA এবং DevOps টিমের shared source of truth হিসেবে ব্যবহৃত হবে।

## 2. অনুমোদিত MVP সিদ্ধান্ত

| বিষয় | সিদ্ধান্ত |
|---|---|
| Client | Browser-based web application |
| Experience | Async clip processing; live virtual camera নয় |
| Appearance | User-uploaded portrait/reference image |
| Motion input | Browser webcam recording |
| Clip duration | ন্যূনতম 5, সর্বোচ্চ 15 সেকেন্ড |
| Processing unit | একটি clip = একটি Runpod job |
| Authentication | User account এবং generation history আবশ্যক |
| Infrastructure | Backend gateway + object storage + Runpod queue endpoint |
| Retention | Default persistent; user-controlled deletion এবং quota প্রযোজ্য |
| Output | MP4 playback এবং download |

## 3. Product reality ও constraint

বর্তমান MimicMotion real-time model নয়। Repository benchmark অনুযায়ী 35 সেকেন্ডের demo RTX 4090-এ প্রায় 20 মিনিট নেয় (`README.md:92-96`)। সুতরাং UI বা marketing copy-তে real-time, live বা instant virtual camera দাবি করা যাবে না।

MimicMotion-এর `chunk_size` একটি inference-এর অভ্যন্তরীণ temporal tile; এটি independent serverless job নয় (`mimicmotion/pipelines/pipeline_mimicmotion.py:539-603`)। একটি recording-কে parallel independent jobs-এ ভাগ করলে latent continuity হারাবে। MVP-তে তাই সম্পূর্ণ 5–15 সেকেন্ড clip এক job-এ process হবে।

## 4. MVP scope

### 4.1 অন্তর্ভুক্ত

1. Account registration, login, logout এবং session management।
2. Portrait upload, preview, selection এবং deletion।
3. Browser camera permission, camera নির্বাচন এবং live preview।
4. 3-second countdown সহ 5–15 সেকেন্ড recording।
5. Recorded clip local preview, retake এবং submit।
6. Browser থেকে presigned URL ব্যবহার করে সরাসরি object storage upload।
7. Backend থেকে asynchronous Runpod `/run` submission।
8. Queue, processing, completion এবং failure status।
9. User cancellation এবং eligible failure retry।
10. Generated MP4 preview, download, history এবং deletion।
11. Per-user ownership, audit trail, quota এবং rate limiting।
12. Worker progress stages, logs এবং operational metrics।

### 4.2 MVP-এর বাইরে

- Real-time/near-real-time virtual camera output।
- Continuous WebRTC stream inference।
- Independent parallel chunk stitching।
- 15 সেকেন্ডের বেশি recording।
- Multi-person motion extraction।
- Audio preservation বা lip-sync।
- Mobile-native/desktop-native app।
- Public sharing link, social feed বা collaboration।
- User-selectable low-level diffusion parameters।
- Billing/subscription checkout; তবে usage records ভবিষ্যতের জন্য রাখা হবে।

## 5. ব্যবহারকারীর end-to-end journey

1. User account তৈরি করে বা login করে।
2. একটি পরিষ্কার single-person portrait upload করে।
3. Camera permission দেয় এবং camera নির্বাচন করে।
4. Framing/lighting নির্দেশনা দেখে 5–15 সেকেন্ড motion record করে।
5. Browser clip preview করে; প্রয়োজন হলে retake করে।
6. User submit করলে browser backend থেকে upload session নেয়।
7. Portrait আগে upload না থাকলে portrait এবং clip object storage-এ যায়।
8. Upload complete acknowledgement-এর পর backend media metadata validate করে।
9. Backend generation এবং attempt record তৈরি করে Runpod `/run` call করে।
10. Browser generation ID পায় এবং status poll করে।
11. Runpod worker input download, preprocess, pose extraction, inference, encode এবং output upload করে।
12. Backend webhook বা reconciliation polling দিয়ে final state sync করে।
13. User history/detail page থেকে result দেখে বা download করে।

## 6. Domain model

### 6.1 User

- একটি account-এর মালিক।
- নিজের portrait, generation এবং media ছাড়া অন্য কারও resource দেখতে পারবে না।
- Active job, daily generation এবং storage quota থাকবে।
- Account deletion অনুরোধ করতে পারবে।

### 6.2 Portrait

- User-owned reference appearance image।
- Original object, validated dimensions, MIME type, checksum এবং optional thumbnail থাকবে।
- Deleted portrait নতুন generation-এ ব্যবহার করা যাবে না।
- Existing generation historical integrity-এর জন্য portrait ID retain করবে; hard delete policy media dependency বিবেচনা করবে।

### 6.3 MediaAsset

Media kinds:

- `PORTRAIT_ORIGINAL`
- `PORTRAIT_THUMBNAIL`
- `MOTION_INPUT`
- `NORMALIZED_INPUT` (optional/debug retention configurable)
- `GENERATED_OUTPUT`
- `OUTPUT_THUMBNAIL`

প্রধান fields: owner, object key, MIME type, byte size, checksum, width, height, FPS, duration, upload state, scan/validation state এবং deletion timestamp।

### 6.4 Generation

একটি user-visible generation request। এতে portrait, motion input, selected model profile, current state, output asset এবং latest attempt থাকবে। Retry হলেও generation ID অপরিবর্তিত থাকবে।

### 6.5 GenerationAttempt

প্রতিটি Runpod submission-এর immutable execution record। Retry নতুন attempt তৈরি করবে। এতে Runpod job ID, parameters snapshot, timestamps, error code এবং execution metrics থাকবে।

### 6.6 UsageRecord

GPU execution, generated seconds, storage bytes এবং success/failure হিসাব রাখবে। ভবিষ্যৎ quota/billing-এর ভিত্তি হবে।

### 6.7 AuditEvent

Login, upload completion, generation submission, retry, cancellation, deletion এবং admin action-এর security-relevant event রাখবে। API key, signed URL বা raw secret audit log-এ রাখা যাবে না।

## 7. State machines

### 7.1 Media upload state

```text
CREATED
  -> UPLOADING
  -> UPLOADED
  -> VALIDATING
  -> READY
```

Terminal/error states:

```text
UPLOAD_EXPIRED
UPLOAD_FAILED
VALIDATION_FAILED
DELETED
```

Client `complete` endpoint call করলেই `READY` হবে না। Backend object head/checksum এবং media validation সফল হওয়ার পর `READY` হবে।

### 7.2 Generation state

```text
DRAFT
  -> VALIDATING
  -> SUBMITTING
  -> QUEUED
  -> IN_PROGRESS
  -> OUTPUT_UPLOADING
  -> COMPLETED
```

Terminal states:

```text
VALIDATION_FAILED
SUBMISSION_FAILED
FAILED
TIMED_OUT
CANCELLED
DELETED
```

### 7.3 State transition rules

- কেবল backend state পরিবর্তন করবে; browser-provided state গ্রহণযোগ্য নয়।
- `COMPLETED`, `FAILED`, `TIMED_OUT` বা `CANCELLED` attempt immutable।
- `COMPLETED` হওয়ার আগে output object existence, non-zero size এবং checksum যাচাই আবশ্যক।
- Cancellation race-এ completion আগে commit হলে completion authoritative; cancellation আগে Runpod acknowledgement পেলে cancelled authoritative। Transaction/locking দিয়ে race resolve করতে হবে।
- Unknown Runpod state internal `IN_PROGRESS` হিসেবে indefinite রাখা যাবে না; reconciliation deadline শেষে `FAILED`/`TIMED_OUT` হবে।

## 8. Input rules

### 8.1 Portrait

- Accepted: JPEG, PNG, WebP।
- Actual file signature MIME-এর সাথে মিলতে হবে।
- Minimum এবং maximum dimensions configuration-এ থাকবে; proposed minimum 512x512।
- Maximum upload size proposed 15 MB।
- Exactly one principal person recommended; face/person না পেলে validation warning বা failure product test অনুযায়ী নির্ধারণ হবে।
- EXIF orientation normalize এবং metadata strip করতে হবে।
- Corrupt, animated বা unsupported color-space image reject করতে হবে।

### 8.2 Motion clip

- Browser-preferred MIME: `video/webm` with VP8/VP9; capability না থাকলে supported MP4 fallback।
- Duration server-side 5.0–15.0 seconds। Browser timer security boundary নয়।
- Maximum upload size proposed 100 MB; production benchmark-এর পর কমানো হবে।
- Audio inference-এ প্রয়োজন নেই এবং normalization-এ বাদ যাবে।
- Worker FFmpeg দিয়ে canonical FPS, dimensions, pixel format এবং codec normalize করবে।
- Zero-frame, corrupt, variable timestamp error অথবা decode failure reject হবে।
- Input-এ একজন clearly visible person থাকা recommended; pose extraction failure user-facing actionable error হবে।

### 8.3 Inference profile

MVP user low-level settings বদলাতে পারবে না। Versioned server-side profile থাকবে, উদাহরণ:

```json
{
  "profile": "mimicmotion-v1.1-balanced-v1",
  "resolution": 576,
  "tile_size": 72,
  "tile_overlap": 6,
  "num_inference_steps": 25,
  "guidance_scale": 2.0,
  "output_fps": 15
}
```

Exact values 5/10/15-second benchmark এবং visual QA শেষে lock করতে হবে। Attempt-এ resolved parameter snapshot রাখতে হবে যাতে পরবর্তী profile change পুরনো result-এর reproducibility নষ্ট না করে।

## 9. Upload business flow

1. Client media kind, content type, byte size এবং checksum দিয়ে upload session চায়।
2. Backend authentication, quota এবং MIME allowlist check করে।
3. Backend opaque object key এবং short-lived single-object presigned upload URL দেয়।
4. Client direct upload করে; application server video bytes proxy করে না।
5. Client upload completion জানায়।
6. Backend object `HEAD`, size এবং checksum verify করে।
7. Async/sync validator metadata extract করে media `READY` করে।
8. Expired incomplete upload cleanup job orphan object/row সরায়।

Object key client ঠিক করতে পারবে না। User filename display metadata হিসেবে sanitized form-এ রাখা যেতে পারে, storage path হিসেবে নয়।

## 10. Generation submission

Preconditions:

- Authenticated এবং active user।
- Portrait ও motion asset একই user-এর এবং `READY`।
- User active-job quota-এর নিচে।
- Idempotency key নতুন অথবা একই payload-এর পূর্ববর্তী request।
- Selected model profile enabled।

Transaction flow:

1. Generation/attempt row create।
2. Input-scoped short-lived signed GET URL এবং output-scoped signed PUT URL create।
3. Worker contract build।
4. Runpod `/run` call; payload-এ binary/base64 থাকবে না।
5. Runpod job ID persist এবং state `QUEUED`।
6. Submission response হারিয়ে গেলে idempotency/reconciliation duplicate job প্রতিরোধ করবে।

Runpod `/run` payload limit 10 MB; object storage URL approach এই সীমা এড়ায়। `/runsync` ব্যবহার করা হবে না, কারণ inference long-running এবং sync retention/wait সীমিত।

## 11. Worker processing rules

1. JSON schema version validate।
2. URL hostname/scheme allowlist এবং generation IDs validate।
3. Job-specific temporary directory তৈরি।
4. Portrait/video download এবং SHA-256 compare।
5. `ffprobe`/decoder দিয়ে authoritative media validation।
6. Motion clip canonical format-এ transcode।
7. DWPose extraction এবং pose quality check।
8. MimicMotion inference; সম্পূর্ণ clip এক call-এ এবং internal tiling ব্যবহার।
9. Reference/generated frame handling existing convention অনুযায়ী।
10. Output H.264 MP4 encode, metadata এবং checksum তৈরি।
11. Signed URL দিয়ে output upload।
12. Optional thumbnail upload।
13. Lightweight JSON result return।
14. `finally` block-এ temporary files delete।

Current Cog path-এর pose shape issue (`predict.py:338` বনাম temporal indexing `mimicmotion/pipelines/pipeline_mimicmotion.py:569`) worker implementation-এর আগে regression test দিয়ে fix করতে হবে।

## 12. Status synchronization

Backend দুই স্তরে status sync করবে:

1. **Primary:** authenticated Runpod webhook/event receipt হলে attempt update।
2. **Safety net:** background reconciler non-terminal jobs-এর `/status/{job_id}` poll করবে।

Browser শুধু application backend poll করবে; Runpod API key বা job-control credentials পাবে না। Proposed polling:

- প্রথম 30 seconds: প্রতি 3–5 seconds।
- পরবর্তী সময়: exponential backoff, maximum 15 seconds।
- Tab hidden হলে slower polling।
- Terminal state-এ polling stop।

## 13. Progress semantics

User-facing stages:

- `UPLOADING`
- `VALIDATING`
- `WAITING_FOR_GPU`
- `PREPARING_POSE`
- `GENERATING`
- `ENCODING`
- `SAVING_OUTPUT`
- `COMPLETED`

Diffusion percentage নির্ভুল না হলে fabricated exact percentage দেখানো যাবে না। Stage, elapsed time এবং non-binding estimate দেখানো যাবে। Runpod `progress_update()` status polling-এ stage প্রকাশ করতে ব্যবহার করা যাবে।

## 14. Retry policy

### 14.1 Automatically retryable

- HTTP 429 বা temporary 5xx।
- Object storage transient timeout।
- Worker infrastructure interruption।
- Runpod job `FAILED`/`TIMED_OUT` যেখানে input deterministic invalid নয়।
- Webhook delivery failure reconciliation দিয়ে recover হবে, নতুন inference নয়।

### 14.2 Non-retryable without user correction

- Invalid/corrupt media।
- Duration/size violation।
- Portrait decode failure।
- Pose not detected বা insufficient pose quality।
- Unsupported profile/schema।
- Authorization/ownership failure।
- User cancellation।

### 14.3 Retry controls

- Automatic attempts proposed maximum 2; benchmark/cost policy পরে lock।
- Exponential backoff এবং jitter।
- Retry একই Generation-এর নতুন GenerationAttempt।
- Runpod `/retry` same job ID ব্যবহার করা যাবে only documented eligible states-এ; auditability-এর জন্য backend attempt mapping স্পষ্ট রাখতে হবে।
- Output key attempt-scoped হবে; successful attempt final output pointer atomically set করবে।

## 15. Cancellation

- `QUEUED` ও `IN_PROGRESS` generation cancel করা যাবে।
- Backend ownership check করে Runpod `/cancel/{job_id}` call করবে।
- UI optimistic terminal state দেখাবে না; `CANCELLING` presentation state ব্যবহার করতে পারে।
- Worker cancellation পেলে temp cleanup এবং partial output delete করার best effort করবে।
- Already completed output cancellation দিয়ে delete হবে না; user আলাদা delete action ব্যবহার করবে।
- GPU execution ইতিমধ্যে হয়ে গেলে incurred cost ফেরত আসে না—UI copy-তে তা উল্লেখ করা যেতে পারে।

## 16. Retention, deletion ও privacy

User persistent retention নির্বাচন করেছে। এর অর্থ unlimited free storage নয়। Rules:

- Input/output default expiry থাকবে না।
- Storage quota per account বাধ্যতামূলক।
- User generation delete করলে portrait dependency ছাড়া associated motion/output objects asynchronous delete হবে।
- Portrait delete হলে নতুন generation-এ unavailable; historical generation policy অনুযায়ী linked snapshot/media retain বা explicit cascade prompt দিতে হবে।
- Account deletion grace period এবং irreversible purge job থাকবে।
- Signed download URL short-lived; public bucket/object নয়।
- Raw camera media logs, analytics বা error tracker-এ পাঠানো যাবে না।
- Privacy notice-এ cloud GPU processing এবং persistent retention স্পষ্ট করতে হবে।

## 17. Quota ও abuse prevention

Configurable initial policy:

- Max concurrent active generations/user: 1।
- Max queued generations/user: 2।
- Daily successful/submitted generation limit।
- Max stored bytes/user।
- Upload session creation rate limit।
- Login/auth rate limit।
- Global Runpod max workers cost cap।
- Admin ability to suspend user এবং cancel queued work।

Quota check submission ও upload—দুই জায়গায় হবে; race এড়াতে database transaction/locking প্রয়োজন।

## 18. Security rules

- Runpod API key browser bundle, HTML, local storage বা response-এ যাবে না।
- Backend/worker secrets environment or secret manager-এ থাকবে।
- Presigned URL least privilege, short expiry এবং single object scope হবে।
- All resource endpoints ownership enforce করবে।
- Webhook authenticity available mechanism দিয়ে verify; না থাকলে untrusted hint হিসেবে ধরে Runpod status API দিয়ে confirm।
- SSRF প্রতিরোধে worker arbitrary client URL গ্রহণ করবে না; backend-issued allowed storage URLs/keys ব্যবহার করবে।
- MIME sniffing, checksum, object size এবং media decoding validation করতে হবে।
- Logs থেকে tokens, authorization headers এবং signed URL query redact করতে হবে।

## 19. Stable error codes

| Code | Retryable | User action |
|---|---:|---|
| `AUTH_REQUIRED` | No | Login |
| `QUOTA_EXCEEDED` | No | পুরনো media delete/অপেক্ষা |
| `UPLOAD_EXPIRED` | Yes | Upload restart |
| `UPLOAD_INCOMPLETE` | Yes | Upload resume/restart |
| `MEDIA_INVALID` | No | New file/recording |
| `DURATION_OUT_OF_RANGE` | No | 5–15 sec record |
| `PORTRAIT_INVALID` | No | Better portrait |
| `POSE_NOT_DETECTED` | No | Better framing/lighting |
| `RUNPOD_RATE_LIMITED` | Yes | Automatic wait |
| `RUNPOD_SUBMISSION_FAILED` | Yes | Retry |
| `RUNPOD_TIMED_OUT` | Conditional | Retry/support |
| `GPU_OUT_OF_MEMORY` | Conditional | Ops/profile fix |
| `OUTPUT_UPLOAD_FAILED` | Yes | Retry attempt |
| `OUTPUT_NOT_FOUND` | Yes | Reconcile/support |
| `GENERATION_CANCELLED` | No | New generation |

Raw stack trace end user-কে দেখানো যাবে না; support/reference ID দেখাতে হবে।

## 20. Notifications

MVP minimum: in-app status। Optional follow-up: email/browser notification। Notification must be idempotent; terminal state প্রতি generation-এ একবার। Output URL notification-এ স্থায়ী public URL হিসেবে দেওয়া যাবে না; authenticated detail page link দিতে হবে।

## 21. Acceptance criteria

### Successful generation

- Given valid logged-in user, ready portrait এবং 5–15 sec clip,
- When user submits once,
- Then exactly one active Runpod job তৈরি হবে,
- And browser refresh-এর পর status recover হবে,
- And successful output user-owned history-তে playable/downloadable হবে।

### Duplicate submission

- Given একই idempotency key এবং একই payload,
- When client timeout-এর পর submit পুনরায় করে,
- Then নতুন generation বা Runpod job তৈরি হবে না।

### Unauthorized access

- Given user A-এর media/generation ID,
- When user B read/download/delete চেষ্টা করে,
- Then generic not-found/forbidden response হবে এবং signed URL দেওয়া হবে না।

### Invalid duration

- Given clip 5 sec-এর কম বা 15 sec-এর বেশি,
- When completion/submit validation হয়,
- Then inference শুরু হবে না এবং actionable error হবে।

### Browser refresh

- Given generation `QUEUED` বা `IN_PROGRESS`,
- When browser refresh/relogin হয়,
- Then database থেকে current state এবং progress ফিরে আসবে; local process state-এর উপর নির্ভর করবে না।

### Worker failure

- Given transient Runpod failure,
- When retry policy allows,
- Then bounded retry হবে, each attempt audited হবে, duplicate final notification হবে না।

### Cancellation

- Given queued/in-progress job,
- When owner cancel করে,
- Then backend Runpod cancel call করবে, terminal state reconcile করবে এবং no unauthorized user cancel করতে পারবে না।

### Deletion

- Given completed generation,
- When owner confirms delete,
- Then it history থেকে অদৃশ্য হবে, signed access revoke হবে এবং asynchronous object purge auditable হবে।

## 22. Definition of Done

MVP complete ধরা হবে যখন:

- 5, 10 এবং 15 সেকেন্ড fixtures production-like Runpod GPU-তে pass করে।
- Pose tensor regression test pass করে।
- User account, upload, submit, status, cancel, retry, playback, history এবং delete end-to-end চলে।
- API key client-এ leak হয় না।
- Object ownership এবং signed URL tests pass করে।
- Queue delay, execution time, failures এবং cost observability dashboard-এ দেখা যায়।
- Recovery tests webhook loss, browser refresh, upload interruption এবং worker timeout cover করে।
- Privacy, retention এবং quota policy UI-তে প্রকাশিত এবং backend-এ enforced।
