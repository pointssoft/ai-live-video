# Repository Agent Notes

## Boundaries and source of truth

- This repository has four independently tooled surfaces: root offline/Cog inference, `apps/web` (Next.js), `apps/api` (FastAPI), and `worker/` (Runpod). Do not mix the API uv environment with the root Conda, Cog, or CUDA worker environments; Cog also declares dependencies independently in `cog.yaml`.
- Run root inference and contract tests from the repository root because configs, sample media, checkpoints, and DWPose ONNX paths are relative (`configs/test.yaml:1-9`, `mimicmotion/dwpose/dwpose_detector.py:69-72`).
- Root `README.md` describes the original inference path, not the web/API/worker product. Prefer code, manifests, migrations, Dockerfiles, workflows, and tests over `plan/` prose.
- GitHub Actions handle deployments:
  - `.github/workflows/build-worker.yml` (and `deploy-worker.yml`) for the batch Runpod worker.
  - `.github/workflows/build-realtime-worker.yml` (and `deploy-realtime-worker.yml`) for the persistent LiveKit WebRTC Runpod Pod.

## Root inference

- Setup: `conda env create -f environment.yaml`, then `conda activate mimicmotion`. This pins Python 3.11, PyTorch 2.0.1, and CUDA 11.7 (`environment.yaml:1-16`). The file omits DWPose imports such as OpenCV, ONNX Runtime, tqdm, and matplotlib.
- Place `MimicMotion_1-1.pth` and both DWPose ONNX files as described in `README.md:53-80`; native inference downloads the configured SVD base model on first use.
- Run `python inference.py --inference_config configs/test.yaml`. Optional flags are `--log_file`, `--output_dir`, and `--no_use_float16`; FP16 is the default (`inference.py:124-138`). Native output defaults to ignored `outputs/`; Cog writes under `/tmp`.
- There is no root lint/typecheck/build or automated diffusion test. Run CPU contract/media tests with `uv run --project apps/api python -m unittest discover -s tests -p "test_*.py" -v`; focus with `-p "test_inference_contract.py"`, `-p "test_worker_contract.py"`, or `-p "test_worker_media.py"`. These do not qualify CUDA inference.

## Web

- `apps/web` requires Node `>=20 <23` and pnpm 10.15.0. Install with `npx pnpm@10.15.0 --dir apps/web install --frozen-lockfile` (`apps/web/package.json:5-13`).
- Verify in order with the same prefix: `run lint`, `run typecheck`, `run test -- --run`, then `run build`. Bare `run test` starts watch mode; focus Vitest with `run test -- --run path/to/file.test.tsx`.
- The browser calls FastAPI directly with credentialed cookie/CSRF requests; Next is not an API proxy. Upload bytes also bypass FastAPI after session creation and go directly to signed object storage (`apps/web/lib/api-client.ts:38-66`, `apps/web/lib/uploads.ts:5-45`).
- Only browser-safe values belong in `NEXT_PUBLIC_*`; the current public setting is `NEXT_PUBLIC_API_BASE_URL`. Auth gating is currently client-side, so do not assume Next middleware protects routes.

## API and local services

- `apps/api` requires Python `>=3.11,<3.13` and its own lockfile. Run `uv sync --project apps/api --frozen --all-groups`. Settings load from `apps/api/.env`, not root `.env`, and required settings are instantiated during imports; a missing API-local environment can fail collection/startup (`apps/api/app/core/config.py:8-45`).
- Verify with `uv run --project apps/api ruff check apps/api`, `uv run --project apps/api mypy apps/api/app`, and `uv run --project apps/api pytest apps/api/tests/unit`. Focus pytest by appending `path/to/test.py::test_name`.
- Start dependencies with `docker compose -f docker/compose.local.yaml up -d postgres minio minio-init`. Migrate with `uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head`; serve with `uv run --project apps/api uvicorn app.main:app --app-dir apps/api --reload`.
- Compose defines PostgreSQL, MinIO, bucket initialization, and `media-validator`, but not FastAPI, Next, or the generation orchestrator. Upload completion intentionally stops at `UPLOADED`; validation advances it to `READY` or `VALIDATION_FAILED`. Host-run validation needs `ffprobe` and `ffmpeg`, which `uv sync` does not install.
- Integration tests require PostgreSQL and MinIO: `uv run --project apps/api pytest apps/api/tests/integration`. With Runpod credentials configured, start orchestration separately: `uv run --project apps/api python -m app.tasks.generation_orchestration` (`apps/api/app/tasks/generation_orchestration.py:653-669`).
- Runpod callbacks use `POST /api/v1/webhooks/runpod`, authenticated by `RUNPOD_WEBHOOK_TOKEN` through `X-Runpod-Webhook-Token` or the configured URL's `token` query fallback. Never log webhook URLs/tokens. Callback payloads are notifications only; terminal state is applied from an authoritative Runpod status fetch. Retries create a new attempt/output key and are bounded by `MAX_GENERATION_ATTEMPTS`.
- `docker/api.Dockerfile` intentionally excludes Torch/CUDA/model dependencies. Local MinIO and production S3-compatible storage share `apps/api/app/services/storage/s3.py`.

## Worker and image CI

- `worker/handler.py` is the Runpod entrypoint. `JobService` validates strict v1 input and signed URLs, checksum-downloads inputs, uses FFprobe to enforce decodability and the declared duration range (the API sends 5–15 seconds), runs inference, uploads and HEAD-verifies MP4 output, and always removes the attempt workspace (`worker/services/job_service.py:22-93`).
- Jobs publish provider-side stages in this order: `VALIDATING_INPUT`, `DOWNLOADING`, `VALIDATING_MEDIA`, `RUNNING_INFERENCE`, `UPLOADING_OUTPUT`, `VERIFYING_OUTPUT`, `COMPLETED`. The API persists the latest worker/provider stage on the current generation attempt and exposes it as `execution.progress_stage`; provider status/output/error remain the Runpod adapter's raw fields (`worker/handler.py:15-25`, `apps/api/app/services/runpod.py:15-70`, `apps/api/app/tasks/generation_orchestration.py:49-95`).
- Production requires nonempty `ALLOWED_STORAGE_HOSTS`, plus `MODEL_ROOT` and `ARTIFACTS_READY_PATH` (defaults `/runpod-volume/models` and `/runpod-volume/ARTIFACTS_READY`). The image contains no models; the ready marker and exact artifact sizes are validated. S3 artifact bootstrap is smoke-only (`worker/config.py:18-31`, `worker/services/model_service.py:31-43`).
- `WORKER_MODE=model-smoke` validates CUDA/artifacts/model loading; `WORKER_MODE=inference-smoke` defaults to expensive real 5/10/15-second generations (`worker/smoke.py:87-263`). Unit tests do not qualify these paths.
- `docker/worker.Dockerfile` pins CUDA 12.1 and Torch 2.3.1. This image failed on Blackwell with `no kernel image is available`; use a validated Ada/Hopper pool or upgrade and rerun GPU qualification.
- `.github/workflows/build-worker.yml` builds `docker/worker.Dockerfile` for `linux/amd64` and publishes release, `phase1-smoke`, and immutable SHA tags. Do not build the CUDA image during routine API verification; note that CI does not build `docker/worker.smoke.Dockerfile`.
- Successful main builds trigger `.github/workflows/deploy-worker.yml`; its `production` environment is the approval gate. Deployment accepts only `sha-<12 lowercase hex>` and patches only the endpoint image. Deploy hard-codes `malaknoyn/mimicmotion-worker`, while build derives the namespace from `DOCKERHUB_USERNAME`; change both together.

## Realtime worker (LiveKit)

- `realtime_worker/main.py` is the entrypoint for the persistent LiveKit worker running on Runpod. It handles WebRTC streaming for realtime face rendering using LivePortrait.
- Runpod deployment relies on manual/trigger updates to `.github/workflows/deploy-realtime-worker.yml`, utilizing GraphQL to interact with Runpod pods. H100 SXM GPUs are required for the `realtime-worker` image due to ONNX runtime CUDA constraints.
- `apps/api/app/api/v1/realtime_sessions.py` handles LiveKit token generation and dispatching to specific worker rooms using explicit `agent_dispatch`. Next.js web connects via `apps/web/components/realtime/RealtimeStudio.tsx`.
- The real-time worker logs `More than one face detected` when `LivePortrait` detects no face. This doesn't crash the session; the worker gracefully falls back to passing through the source image frame (`source.image`) directly.

## Inference invariants

- Pose tensors are exactly `[T, 3, H, W]`, with reference pose at index `0`; a batch dimension is invalid. Route native/Cog/worker calls through `mimicmotion/utils/inference_contract.py` and rerun root tests after changes.
- `num_frames` passed to the pipeline is total sampled pose length; requested tile size is separate. Tile overlap must be nonnegative and less than the effective tile size (`mimicmotion/utils/inference_contract.py:38-82`).
- Preserve overlapping temporal tiles. Never split a clip into independent inference jobs and stitch outputs: tiles share weighted latent/scheduler progression (`mimicmotion/pipelines/pipeline_mimicmotion.py:565-609`).
- Assume NVIDIA/CUDA for diffusion: the pipeline enters an unconditional CUDA context despite CPU fallback selection in entrypoints (`mimicmotion/pipelines/pipeline_mimicmotion.py:558-564`).
- Pipeline conditioning uses `fps=7`; YAML/profile output FPS controls MP4 playback and is separate (`inference.py:72-81`, `inference.py:107-113`).
- Cog mutates process-global default torch dtype and replaces its cached pipeline when checkpoint selection changes; concurrent requests using different checkpoints are not isolated (`predict.py:166-189`).
- DWPose sampling adjusts stride by source FPS and globally affine-fits detections across the clip; poor or inconsistent single-person detections can fail before diffusion (`mimicmotion/dwpose/preprocess.py:32-49`).
