# Repository Agent Notes

## Source of truth

- The repository contains two separate systems: the original offline MimicMotion inference and a web/API foundation under `apps/`, plus a worker shell under `worker/`. Upload validation, portrait-library APIs, browser camera/direct-upload flows, and the versioned worker contract now exist; GPU artifact bootstrap, generation orchestration, and production Runpod deployment are not verified yet. Do not present planning documents as executable behavior (`plan/file-tree.md:451-462`).
- Run commands from the repository root. Config, example media, checkpoints, and DWPose ONNX paths are relative (`configs/test.yaml:1-9`, `mimicmotion/dwpose/dwpose_detector.py:69-72`).

## Setup and execution

- Native setup: `conda env create -f environment.yaml`, then `conda activate mimicmotion` (`README.md:44-51`). The environment pins Python 3.11, PyTorch 2.0.1, and CUDA 11.7.
- `environment.yaml` is incomplete for imports used by the code: OpenCV, ONNX Runtime, tqdm, and matplotlib are absent. `cog.yaml` includes them but uses substantially newer dependency ranges; do not assume the native and Cog environments are equivalent.
- Follow `README.md:53-80` to place the two DWPose ONNX files and `MimicMotion_1-1.pth` under `models/`. Native inference downloads the configured SVD base model from Hugging Face on first use.
- Sample run: `python inference.py --inference_config configs/test.yaml`. Optional CLI flags are `--output_dir` and `--no_use_float16` (`inference.py:122-135`); FP16 is the default.
- Native outputs are timestamped logs and MP4s under ignored `outputs/`. Cog writes timestamped MP4s under `/tmp` (`inference.py:105-111`, `predict.py:278-282`).
- Offline inference has no automated test, lint, formatter, type-check, or native build command. `configs/test.yaml` is an inference profile, not a test suite.

## Web/API foundation

- `apps/web` is an independent Next.js 15/pnpm app. Use Node 20 or 22, then run `npx pnpm@10.15.0 --dir apps/web install --frozen-lockfile`, followed by `lint`, `typecheck`, `test --run`, and `build` through the same `npx pnpm... --dir apps/web` prefix (`apps/web/package.json:5-14`).
- `apps/api` is an independent Python 3.11+ uv project; never install its dependencies into the CUDA Conda environment. Run `uv sync --project apps/api --all-groups`, then Ruff, mypy, and pytest using `uv run --project apps/api ...` (`apps/api/pyproject.toml:1-43`).
- API settings load from `apps/api/.env`; copy `.env.example`. Run migrations with `uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head`, then serve with `uv run --project apps/api uvicorn app.main:app --app-dir apps/api --reload`.
- Local PostgreSQL, MinIO, and the media-validator process are defined in `docker/compose.local.yaml`. Docker is required for migrations and integration verification; direct upload completion intentionally stops at `UPLOADED`, and the validator advances assets through `VALIDATING` to `READY` or `VALIDATION_FAILED`.
- Web auth uses opaque HttpOnly API cookies plus double-submit CSRF. Production needs sibling custom domains for Vercel and Railway; do not put database, R2, session, or future Runpod secrets in `NEXT_PUBLIC_*` variables.
- `docker/api.Dockerfile` is the Railway API image and intentionally excludes all Torch/CUDA/model dependencies. Cloudflare R2 and local MinIO share the S3-compatible adapter at `apps/api/app/services/storage/s3.py`.
- `worker/` is a versioned, independently deployable Runpod worker shell. It uses strict input contracts, signed-URL host/path validation, UUID workspaces, and injected storage/model services; it has not been GPU/model-artifact qualified yet. `docker/worker.Dockerfile` is a CUDA image and should not be built as part of normal API verification.
## Code boundaries

- `inference.py`: native CLI orchestration and the most reliable reference flow.
- `predict.py`: separate Cog/Replicate adapter selected by `cog.yaml`; no local Cog command is documented.
- `mimicmotion/utils/loader.py`: model assembly and checkpoint loading.
- `mimicmotion/dwpose/`: reference-image and motion-video pose extraction/normalization.
- `mimicmotion/pipelines/pipeline_mimicmotion.py`: long-video tiled diffusion and device movement.
- `mimicmotion/utils/utils.py`: MP4 writing.

## Inference invariants and traps

- Preserve the pipeline's overlapping temporal tiles. Do not split one clip into independent inference jobs and stitch outputs; tiles share weighted latent/scheduler progression (`mimicmotion/pipelines/pipeline_mimicmotion.py:539-603`).
- `task.num_frames` is the tile size, not total output length. The sampled pose tensor length determines generated duration (`inference.py:64-75`). Keep `frames_overlap < num_frames`; only the Cog path validates this.
- Assume NVIDIA/CUDA for inference. Although entrypoints select CPU when CUDA is unavailable, the pipeline enters an unconditional CUDA device context (`mimicmotion/pipelines/pipeline_mimicmotion.py:546-550`).
- Pose tensors use the strict `[T, 3, H, W]` contract, with the reference pose at index `0`; a batch dimension is invalid. Keep native, Cog, and future worker calls routed through `mimicmotion/utils/inference_contract.py`, and run `uv run --project apps/api python -m unittest discover -s tests -p "test_*.py" -v` after changing the contract.
- Cog mutates the process-global default torch dtype and replaces its cached pipeline when checkpoint selection changes (`predict.py:166-189`); concurrent predictions with different checkpoints are not isolated.
- Source sampling stride is adjusted by source FPS, and DWPose globally affine-fits detections across the clip (`mimicmotion/dwpose/preprocess.py:32-49`). Poor or inconsistent single-person detections can fail before diffusion.
- The pipeline is conditioned with `fps=7`; the YAML task `fps` controls MP4 playback rate, not the same value (`inference.py:68-75`, `inference.py:105-111`).
