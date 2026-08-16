# Repository Agent Notes

## Boundaries and source of truth

- This is four independently tooled surfaces: root offline/Cog inference, `apps/web` (Next.js), `apps/api` (FastAPI), and `worker/` (Runpod). Do not mix the API uv environment with the CUDA Conda/worker environments.
- Run root inference and contract-test commands from the repository root: configs, sample media, checkpoints, and DWPose ONNX paths are relative (`configs/test.yaml:1-9`, `mimicmotion/dwpose/dwpose_detector.py:69-72`).
- Root `README.md` documents the original inference path, not the newer web/API/worker implementation. Treat code, manifests, migrations, Dockerfiles, and tests as authoritative; planning files are not executable behavior.

## Root inference

- Setup: `conda env create -f environment.yaml`, then `conda activate mimicmotion`. This pins Python 3.11, PyTorch 2.0.1, and CUDA 11.7 (`environment.yaml:1-16`).
- `environment.yaml` omits imports used by DWPose (OpenCV, ONNX Runtime, tqdm, matplotlib). Cog and worker use different/newer dependency sets; success in one environment does not qualify another.
- Place `MimicMotion_1-1.pth` and both DWPose ONNX files as described in `README.md:53-80`; native inference downloads the configured SVD base model on first use.
- Run `python inference.py --inference_config configs/test.yaml`. Optional flags are `--log_file`, `--output_dir`, and `--no_use_float16`; FP16 is the default (`inference.py:124-138`). Native output defaults to ignored `outputs/`; Cog writes under `/tmp`.
- There is no automated full diffusion/GPU test or root lint/typecheck/build command. Root tests cover contracts only: `uv run --project apps/api python -m unittest discover -s tests -p "test_*.py" -v`. Run a focused test with `... -p "test_inference_contract.py" -v` or `... -p "test_worker_contract.py" -v`.

## Web

- `apps/web` requires Node `>=20 <23` and pnpm 10.15.0. Install with `npx pnpm@10.15.0 --dir apps/web install --frozen-lockfile` (`apps/web/package.json:5-13`).
- Verify in order with the same prefix: `run lint`, `run typecheck`, `run test -- --run`, then `run build`. Focus Vitest with `run test -- --run path/to/file.test.tsx`.
- Only browser-safe configuration belongs in `NEXT_PUBLIC_*`; the current public setting is `NEXT_PUBLIC_API_BASE_URL`. Database, storage, session, and Runpod credentials are API-only.

## API and local services

- `apps/api` requires Python `>=3.11,<3.13` and its own lockfile. Run `uv sync --project apps/api --frozen --all-groups`; settings load from `apps/api/.env`, not root `.env` (`apps/api/app/core/config.py:8-14`).
- Verify with `uv run --project apps/api ruff check apps/api`, `uv run --project apps/api mypy apps/api/app`, and `uv run --project apps/api pytest apps/api/tests/unit`. Focus pytest by appending `path/to/test.py::test_name`.
- Start local dependencies with `docker compose -f docker/compose.local.yaml up -d postgres minio minio-init`. Migrations need reachable PostgreSQL: `uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head`. Serve with `uv run --project apps/api uvicorn app.main:app --app-dir apps/api --reload`.
- Integration tests require PostgreSQL and MinIO: `uv run --project apps/api pytest apps/api/tests/integration`. Compose separately runs `media-validator`; upload completion intentionally stops at `UPLOADED`, then validation advances to `READY` or `VALIDATION_FAILED` (`docker/compose.local.yaml:48-71`).
- Generation routes and Runpod orchestration exist, but Compose does not start the orchestrator. With `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID` configured, run `uv run --project apps/api python -m app.tasks.generation_orchestration` (`apps/api/app/tasks/generation_orchestration.py:423-439`).
- `docker/api.Dockerfile` intentionally excludes Torch/CUDA/model dependencies. Local MinIO and production S3-compatible storage share `apps/api/app/services/storage/s3.py`.

## Worker and image CI

- `worker/handler.py` is the Runpod entrypoint. It validates a strict versioned contract, uses UUID workspaces, validates signed URL host/path and hashes, uploads MP4 output, verifies it with HEAD, and cleans up through `JobService`.
- Normal worker execution expects a populated `MODEL_ROOT` and `ARTIFACTS_READY_PATH`. S3 artifact bootstrap exists only in smoke tooling (`worker/smoke.py:11-64`). `WORKER_MODE=model-smoke` validates CUDA/artifacts/model loading; `WORKER_MODE=inference-smoke` defaults to expensive 5/10/15-second real generations (`worker/smoke.py:87-263`). Unit tests do not qualify these GPU paths.
- `.github/workflows/build-worker.yml` builds only `linux/amd64` on relevant `main` changes or manual dispatch. It requires repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`, and publishes release, `phase1-smoke`, and commit-SHA tags (`.github/workflows/build-worker.yml:31-128`). Do not build the CUDA worker image as part of routine API verification.
- A successful main-branch worker build triggers `.github/workflows/deploy-worker.yml`. Its `production` environment is the manual approval gate; configure required reviewers plus environment secrets `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID` in GitHub. It patches only the endpoint image to an immutable `sha-<12 hex>` tag and leaves all other Runpod settings unchanged.

## Inference invariants

- Pose tensors are exactly `[T, 3, H, W]`, with reference pose at index `0`; a batch dimension is invalid. Route native/Cog/worker calls through `mimicmotion/utils/inference_contract.py` and rerun root contract tests after changes.
- `num_frames` passed to the pipeline is total sampled pose length; requested tile size is separate. Tile overlap must be nonnegative and less than the effective tile size (`mimicmotion/utils/inference_contract.py:38-82`).
- Preserve overlapping temporal tiles. Never split a clip into independent inference jobs and stitch outputs: tiles share weighted latent/scheduler progression (`mimicmotion/pipelines/pipeline_mimicmotion.py:565-609`).
- Assume NVIDIA/CUDA for diffusion: the pipeline enters an unconditional CUDA device context despite CPU fallback selection in entrypoints (`mimicmotion/pipelines/pipeline_mimicmotion.py:558-564`).
- Pipeline conditioning uses `fps=7`; YAML/profile output FPS controls MP4 playback and is separate (`inference.py:72-81`, `inference.py:107-113`).
- Cog mutates process-global default torch dtype and replaces its cached pipeline when checkpoint selection changes; concurrent requests using different checkpoints are not isolated (`predict.py:166-189`).
- DWPose sampling adjusts stride by source FPS and globally affine-fits detections across the clip; poor or inconsistent single-person detections can fail before diffusion (`mimicmotion/dwpose/preprocess.py:32-49`).
