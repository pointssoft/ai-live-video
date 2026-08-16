# Proposed File and Directory Structure

## 1. উদ্দেশ্য

এই ডকুমেন্টে বর্তমান MimicMotion research repository-কে production web platform-এ সম্প্রসারণের target file tree, প্রতিটি module-এর responsibility, dependency rules এবং existing code migration plan দেওয়া হয়েছে। এটি implementation roadmap; সব file একসাথে তৈরি করা বাধ্যতামূলক নয়। Phase অনুযায়ী প্রয়োজনীয় file তৈরি হবে।

## 2. Current repository summary

বর্তমান root-এর গুরুত্বপূর্ণ অংশ:

```text
MimicMotion/
├── assets/
├── configs/
├── mimicmotion/
│   ├── dwpose/
│   ├── modules/
│   ├── pipelines/
│   └── utils/
├── cog.yaml
├── constants.py
├── environment.yaml
├── inference.py
├── predict.py
└── README.md
```

`mimicmotion/` model core হিসেবে reuse হবে। `inference.py` CLI/reference path এবং `predict.py` Cog adapter হিসেবে থাকবে বা deprecation plan পাবে; production Runpod worker আলাদা adapter হবে।

## 3. Target repository tree

```text
MimicMotion/
├── apps/
│   ├── web/
│   │   ├── app/
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx
│   │   │   │   ├── register/page.tsx
│   │   │   │   └── layout.tsx
│   │   │   ├── (app)/
│   │   │   │   ├── dashboard/page.tsx
│   │   │   │   ├── create/page.tsx
│   │   │   │   ├── generations/page.tsx
│   │   │   │   ├── generations/[id]/page.tsx
│   │   │   │   ├── portraits/page.tsx
│   │   │   │   ├── settings/page.tsx
│   │   │   │   └── layout.tsx
│   │   │   ├── error.tsx
│   │   │   ├── not-found.tsx
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx
│   │   ├── components/
│   │   │   ├── camera/
│   │   │   │   ├── CameraPermission.tsx
│   │   │   │   ├── CameraPreview.tsx
│   │   │   │   ├── CameraSelector.tsx
│   │   │   │   ├── FramingGuide.tsx
│   │   │   │   ├── RecordingControls.tsx
│   │   │   │   └── RecordingPreview.tsx
│   │   │   ├── generations/
│   │   │   │   ├── GenerationCard.tsx
│   │   │   │   ├── GenerationStatus.tsx
│   │   │   │   ├── GenerationTimeline.tsx
│   │   │   │   ├── GenerationActions.tsx
│   │   │   │   └── OutputPlayer.tsx
│   │   │   ├── portraits/
│   │   │   │   ├── PortraitPicker.tsx
│   │   │   │   ├── PortraitUploader.tsx
│   │   │   │   └── PortraitCard.tsx
│   │   │   ├── uploads/
│   │   │   │   ├── UploadProgress.tsx
│   │   │   │   └── UploadError.tsx
│   │   │   └── ui/
│   │   ├── hooks/
│   │   │   ├── useCamera.ts
│   │   │   ├── useMediaRecorder.ts
│   │   │   ├── useDirectUpload.ts
│   │   │   ├── useGeneration.ts
│   │   │   └── useGenerationPolling.ts
│   │   ├── lib/
│   │   │   ├── api-client.ts
│   │   │   ├── auth.ts
│   │   │   ├── media-capabilities.ts
│   │   │   ├── errors.ts
│   │   │   └── format.ts
│   │   ├── types/
│   │   │   ├── api.ts
│   │   │   ├── generation.ts
│   │   │   └── media.ts
│   │   ├── tests/
│   │   │   ├── camera/
│   │   │   ├── generations/
│   │   │   └── e2e/
│   │   ├── public/
│   │   ├── next.config.*
│   │   ├── package.json
│   │   └── tsconfig.json
│   │
│   └── api/
│       ├── app/
│       │   ├── main.py
│       │   ├── api/
│       │   │   ├── dependencies.py
│       │   │   └── v1/
│       │   │       ├── router.py
│       │   │       ├── auth.py
│       │   │       ├── users.py
│       │   │       ├── uploads.py
│       │   │       ├── portraits.py
│       │   │       ├── generations.py
│       │   │       └── webhooks.py
│       │   ├── auth/
│       │   │   ├── password.py
│       │   │   ├── sessions.py
│       │   │   └── tokens.py
│       │   ├── core/
│       │   │   ├── config.py
│       │   │   ├── errors.py
│       │   │   ├── logging.py
│       │   │   ├── security.py
│       │   │   └── telemetry.py
│       │   ├── db/
│       │   │   ├── base.py
│       │   │   ├── session.py
│       │   │   └── transaction.py
│       │   ├── models/
│       │   │   ├── user.py
│       │   │   ├── portrait.py
│       │   │   ├── media_asset.py
│       │   │   ├── generation.py
│       │   │   ├── generation_attempt.py
│       │   │   ├── usage_record.py
│       │   │   ├── audit_event.py
│       │   │   └── outbox_event.py
│       │   ├── repositories/
│       │   │   ├── users.py
│       │   │   ├── media.py
│       │   │   ├── portraits.py
│       │   │   ├── generations.py
│       │   │   └── attempts.py
│       │   ├── schemas/
│       │   │   ├── auth.py
│       │   │   ├── uploads.py
│       │   │   ├── portraits.py
│       │   │   ├── generations.py
│       │   │   ├── runpod.py
│       │   │   └── common.py
│       │   ├── services/
│       │   │   ├── upload_service.py
│       │   │   ├── portrait_service.py
│       │   │   ├── generation_service.py
│       │   │   ├── generation_state.py
│       │   │   ├── quota_service.py
│       │   │   ├── media_validation.py
│       │   │   ├── playback_service.py
│       │   │   ├── storage/
│       │   │   │   ├── base.py
│       │   │   │   └── s3.py
│       │   │   └── runpod/
│       │   │       ├── client.py
│       │   │       ├── contracts.py
│       │   │       ├── mapper.py
│       │   │       └── webhook.py
│       │   ├── tasks/
│       │   │   ├── scheduler.py
│       │   │   ├── reconcile_jobs.py
│       │   │   ├── cleanup_uploads.py
│       │   │   ├── purge_media.py
│       │   │   └── retry_attempts.py
│       │   └── middleware/
│       │       ├── request_id.py
│       │       ├── rate_limit.py
│       │       └── error_handler.py
│       ├── migrations/
│       │   ├── env.py
│       │   └── versions/
│       ├── tests/
│       │   ├── unit/
│       │   ├── integration/
│       │   ├── contract/
│       │   └── fixtures/
│       └── pyproject.toml
│
├── worker/
│   ├── handler.py
│   ├── bootstrap.py
│   ├── config.py
│   ├── contracts.py
│   ├── errors.py
│   ├── progress.py
│   ├── workspace.py
│   ├── services/
│   │   ├── job_service.py
│   │   ├── model_service.py
│   │   ├── pose_service.py
│   │   ├── media_service.py
│   │   ├── storage_service.py
│   │   └── manifest_service.py
│   ├── profiles/
│   │   └── mimicmotion-v1.1-balanced-v1.yaml
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── gpu/
│   │   ├── fixtures/
│   │   └── test_input.json
│   └── requirements.lock
│
├── mimicmotion/
│   ├── dwpose/
│   ├── modules/
│   ├── pipelines/
│   └── utils/
│
├── docker/
│   ├── web.Dockerfile
│   ├── api.Dockerfile
│   ├── worker.Dockerfile
│   └── compose.local.yaml
│
├── infra/
│   ├── environments/
│   │   ├── staging/
│   │   └── production/
│   ├── runpod/
│   │   ├── endpoint-settings.example.json
│   │   └── deploy-notes.txt
│   └── storage/
│       ├── cors.example.json
│       └── lifecycle.example.json
│
├── scripts/
│   ├── benchmark_worker.py
│   ├── verify_model_artifacts.py
│   ├── create_test_media.py
│   └── smoke_runpod_endpoint.py
│
├── tests/
│   ├── benchmarks/
│   │   ├── cases.yaml
│   │   └── results/
│   ├── fixtures/
│   └── visual/
│
├── plan/
│   ├── BusinessLogic.md
│   ├── DFD.md
│   ├── Architect.md
│   ├── file-tree.md
│   └── UI-UX.md
│
├── .github/
│   └── workflows/
│       ├── web-api-ci.yaml
│       ├── worker-ci.yaml
│       └── worker-gpu-smoke.yaml
│
├── configs/
├── assets/
├── inference.py
├── predict.py
├── cog.yaml
├── environment.yaml
├── constants.py
├── README.md
└── LICENSE
```

## 4. Web application responsibilities

### `app/(auth)/`

Unauthenticated routes। Authentication forms শুধু API call এবং validation orchestrate করবে; raw auth logic components-এ ছড়ানো যাবে না।

### `app/(app)/create/page.tsx`

Create wizard composition। Camera implementation সরাসরি page-এ নয়; hooks/components ব্যবহার করবে। Page state machine:

```text
PORTRAIT -> CAMERA_SETUP -> RECORDING -> REVIEW -> UPLOADING -> SUBMITTED
```

### `components/camera/`

- `CameraPermission.tsx`: rationale, request এবং denial recovery।
- `CameraSelector.tsx`: `enumerateDevices()` output।
- `CameraPreview.tsx`: MediaStream attach/detach lifecycle।
- `FramingGuide.tsx`: portrait orientation এবং body placement overlay।
- `RecordingControls.tsx`: countdown, start/stop, hard duration limit।
- `RecordingPreview.tsx`: Blob playback, duration এবং retake।

### `hooks/useCamera.ts`

`getUserMedia`, device switch, track cleanup এবং permission/device errors encapsulate করবে। UI text render করবে না।

### `hooks/useMediaRecorder.ts`

Supported MIME detect, chunk accumulation, timer এবং Blob creation। Browser capability-independent typed state expose করবে।

### `hooks/useDirectUpload.ts`

Upload session create, signed PUT, progress, abort এবং expired URL recovery। Runpod সম্পর্কে জানবে না।

### `hooks/useGenerationPolling.ts`

Application API poll করবে, terminal state-এ stop এবং hidden tab backoff করবে। Runpod statuses UI-তে সরাসরি leak না করে application state ব্যবহার করবে।

### `lib/api-client.ts`

Central fetch wrapper:

- Base URL।
- credentials/session।
- request ID/error parsing।
- abort/timeout।
- Stable error type।

Secrets বা Runpod endpoint ID এখানে রাখা যাবে না।

## 5. API responsibilities

### `main.py`

App factory, middleware, routers, startup health। Heavy ML import/API process-এ থাকবে না।

### `core/config.py`

Environment variables typed settings। Production startup missing secret/config-এ fail fast। Config categories:

- DB।
- Auth।
- Storage bucket/region/endpoint।
- Runpod API endpoint/key।
- Limits/timeouts।
- Observability।

### `models/`

Database persistence only। Business transitions model method-এ scattered না করে service/state module-এ centralize করা preferred।

### `repositories/`

Database query/locking abstraction। HTTP, Runpod বা S3 call করবে না।

### `schemas/`

External/internal contracts। ORM model API response হিসেবে সরাসরি return করা যাবে না। `runpod.py` worker contract backend copy নয়—shared schema generation/versioning strategy বিবেচনা করতে হবে।

### `services/generation_state.py`

Allowed state transition matrix-এর single source। Out-of-order webhook, cancel race এবং retry transitions test করবে।

### `services/runpod/client.py`

Only module authorized to construct Runpod URLs/auth headers। Operations:

```text
submit_job
get_status
cancel_job
retry_job (if used)
get_health
```

429 exponential backoff, timeouts, response validation, redacted logs।

### `services/storage/`

Vendor-neutral interface:

```text
create_upload_url
create_download_url
create_output_upload_url
head_object
delete_object(s)
```

Object key server-generated হবে।

### `tasks/reconcile_jobs.py`

Leased batch-এ non-terminal attempts নিয়ে Runpod status fetch এবং idempotent state update। Multiple scheduler process duplicate work না করার locking।

### `tasks/purge_media.py`

Soft-deleted records-এর object delete, retry এবং audit। Generation API synchronous object deletion অপেক্ষা করবে না।

## 6. Worker responsibilities

### `handler.py`

Thin Runpod entry point:

```python
from worker.bootstrap import application
import runpod

runpod.serverless.start({"handler": application.handle})
```

Actual code style package/import layout অনুযায়ী হবে। `handler.py`-তে model logic, FFmpeg command construction বা storage logic রাখা যাবে না।

### `bootstrap.py`

Startup order:

1. Config validate।
2. Fitness checks।
3. Model artifacts resolve।
4. DWPose + MimicMotion load।
5. Services compose।
6. Ready to accept one job।

### `contracts.py`

Strict versioned job schema। Unknown version reject, URL hosts validate, numeric bounds enforce।

### `services/job_service.py`

Job orchestration এবং `try/finally` cleanup। Domain-specific error typed code-এ map।

### `services/model_service.py`

Existing loader/pipeline adapter। Responsibilities:

- Fixed model/version initialize।
- Device/dtype।
- Inference lock/assert single concurrency।
- Pose tensor shape contract।
- Progress callback।
- Output frame conversion।

### `services/media_service.py`

Safe subprocess argument list দিয়ে `ffprobe`/FFmpeg। Shell interpolation নয়। Probe, transcode, encode, thumbnail এবং metadata।

### `services/storage_service.py`

Streaming download with maximum byte guard, SHA-256, timeout এবং upload verification। Signed URL log redaction।

### `workspace.py`

Attempt-specific path, file names, disk usage checks এবং deterministic cleanup।

### `profiles/*.yaml`

Ops-reviewed profile। Handler arbitrary client override নয়; backend snapshot values এবং worker allowlisted profile/version consistency যাচাই করবে।

## 7. Existing code migration map

| Existing location | Target/reuse | Required action |
|---|---|---|
| `mimicmotion/utils/loader.py` | Worker model service dependency | Stable loader API; artifact path configurable |
| `mimicmotion/dwpose/preprocess.py` | Pose service | Errors/quality handling, temp/input normalization integration |
| `mimicmotion/pipelines/pipeline_mimicmotion.py` | Core pipeline | Preserve internal tiling; regression tests |
| `mimicmotion/utils/utils.py` | Media service candidate | Production encode error handling; FFmpeg/imageio policy review |
| `inference.py` | CLI/dev reference | Keep thin or route through shared service later |
| `predict.py` | Legacy Cog adapter | Fix shape bug if retained; do not couple Runpod handler to Cog |
| `cog.yaml` | Legacy deployment | Keep until explicitly retired |
| `configs/test.yaml` | Benchmark reference | Convert approved values into versioned worker profile |

## 8. Dependency direction rules

```text
Web pages -> Web components/hooks -> API client/types

API routes -> Services -> Repositories/External clients
Repositories -> Database models/session
External clients -> Config/contracts
Tasks -> Services/repositories

Worker handler -> Job service -> Model/Media/Storage services
Model service -> mimicmotion core
mimicmotion core -X-> API/Web/Runpod HTTP
```

Prohibited dependencies:

- `mimicmotion/` importing `apps/api` বা `worker/handler`।
- Web code importing server secrets/config।
- API routes making raw S3/Runpod calls bypassing services।
- Database repository calling external APIs।
- Worker connecting directly to product DB।
- Frontend knowing Runpod API key or endpoint operations।

## 9. Shared contracts strategy

Backend Python এবং frontend TypeScript types drift ঠেকাতে:

1. FastAPI OpenAPI থেকে frontend types/client generate, অথবা
2. CI contract fixtures compare।

Backend ↔ worker contract Python packages হলেও version field এবং golden JSON fixtures দুই code path-এ test করতে হবে। Worker image API deploy-এর সাথে lockstep ধরে নেওয়া যাবে না; backward-compatible schema rollout দরকার।

Suggested rollout:

1. Worker supports old + new schema।
2. Deploy worker।
3. Backend starts sending new schema।
4. Old schema usage zero হলে remove।

## 10. Configuration and secrets

Example variable groups (actual secret values commit নয়):

```text
APP_ENV
DATABASE_URL
SESSION_SECRET / JWT_PRIVATE_KEY
WEB_ALLOWED_ORIGINS
S3_ENDPOINT_URL
S3_REGION
S3_BUCKET
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
RUNPOD_API_KEY
RUNPOD_ENDPOINT_ID
RUNPOD_EXECUTION_TIMEOUT_MS
RUNPOD_JOB_TTL_MS
MAX_CLIP_DURATION_SECONDS
MAX_ACTIVE_GENERATIONS_PER_USER
MAX_STORAGE_BYTES_PER_USER
```

Worker:

```text
RUNPOD_INIT_TIMEOUT
MODEL_VERSION
MODEL_ROOT
MODEL_PROFILE_PATH
ALLOWED_STORAGE_HOSTS
WORKSPACE_ROOT
MAX_INPUT_BYTES
LOG_LEVEL
```

`.env` production source নয়; secret manager/platform environment ব্যবহার করতে হবে। `.env.example` তৈরি হলে placeholders only।

## 11. Storage naming

```text
users/{user_id}/portraits/{portrait_id}/original.{ext}
users/{user_id}/portraits/{portrait_id}/thumbnail.jpg
users/{user_id}/generations/{generation_id}/input/{asset_id}.{ext}
users/{user_id}/generations/{generation_id}/attempts/{attempt_no}/output.mp4
users/{user_id}/generations/{generation_id}/attempts/{attempt_no}/thumbnail.jpg
```

Rules:

- IDs UUID/opaque।
- Original filename path-এ নয়।
- Temporary upload prefix optional; completion-এর পর move/copy policy provider capability অনুযায়ী।
- Output key backend generates; worker returns same key।
- Bucket private।

## 12. Test file organization

### Web

- Unit: MIME selection, timer, state reducers।
- Component: permission/error/status UI।
- E2E: mocked camera MediaStream and upload/generation APIs।

### API

- Unit: state machine, quota, retry, mapper।
- Integration: real PostgreSQL এবং S3 emulator/test service।
- Contract: OpenAPI, Runpod fixtures, webhook order।

### Worker

- Unit: contracts, URL allowlist, manifests, errors।
- Integration CPU: media probe/transcode/download/upload।
- GPU: pipeline smoke/shape/VRAM।
- Visual regression: human review + optional metrics; no simplistic pixel equality for diffusion।

### Root benchmark

`tests/benchmarks/results/` generated large result commit না করার policy প্রয়োজন। Metadata JSON/CSV commit করা যেতে পারে; media artifacts external controlled storage-এ।

## 13. Build order by files

### Stage A — Worker proof

```text
worker/config.py
worker/contracts.py
worker/errors.py
worker/workspace.py
worker/services/media_service.py
worker/services/storage_service.py
worker/services/model_service.py
worker/services/job_service.py
worker/bootstrap.py
worker/handler.py
docker/worker.Dockerfile
worker/tests/...
```

### Stage B — API foundation

```text
apps/api/app/core/*
apps/api/app/db/*
apps/api/app/models/*
apps/api/migrations/*
apps/api/app/auth/*
apps/api/app/services/storage/*
apps/api/app/services/runpod/*
```

### Stage C — Product API

```text
uploads.py / upload_service.py
portraits.py / portrait_service.py
generations.py / generation_service.py / generation_state.py
tasks/reconcile_jobs.py
tasks/purge_media.py
```

### Stage D — Web

```text
lib/api-client.ts
hooks/useCamera.ts
hooks/useMediaRecorder.ts
hooks/useDirectUpload.ts
camera components
create page
generation polling/status/history/detail
```

### Stage E — Operations

```text
docker/*
infra/*
.github/workflows/*
scripts/benchmark_worker.py
scripts/smoke_runpod_endpoint.py
```

## 14. Naming and code conventions

- Python modules/functions: `snake_case`; classes `PascalCase`।
- TypeScript components/types: `PascalCase`; hooks `useX`।
- DB enum values and API state strings uppercase stable tokens।
- Times UTC এবং ISO-8601 externally।
- Durations explicit unit suffix (`_ms`, `_seconds`)।
- Byte sizes `_bytes`।
- IDs typed UUID internally; external string representation।
- No generic `utils.py` growth in new application modules; domain-named helpers। Existing model utilities gradually refactor only when needed।

## 15. Files intentionally not proposed

- Separate microservice per domain: MVP complexity unnecessary।
- Redis required from day one: DB-backed reconciler/outbox adequate initially; measured need হলে add।
- WebSocket service: status polling sufficient for slow async jobs।
- Client-side Runpod SDK: security violation।
- Chunk coordinator/stitcher: model continuity violation for MVP।
- Public media CDN URL: private persistent media requirement-এর সাথে অসামঞ্জস্য।

## 16. Repository hygiene

- Large model weights/media fixtures Git-এ commit নয়।
- `.dockerignore` worker build context review; current ignored model policy artifact strategy অনুযায়ী update।
- Lock dependencies; GPU/CUDA/PyTorch compatibility document/test।
- Generated output, local DB, `.env`, test secrets ignore।
- New docs only when required; এই `plan/` files implementation source।
- Existing Cog compatibility change করলে targeted tests এবং migration note আবশ্যক।
