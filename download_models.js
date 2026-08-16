#!/usr/bin/env node
/**
 * Download and verify the model artifacts required by MimicMotion.
 *
 * Run from the repository root on Linux with Node.js 20+:
 *   node download_models.js
 *
 * Optional environment variables:
 *   HF_TOKEN       Hugging Face access token.
 *   HF_ENDPOINT    Hugging Face endpoint, e.g. https://hf-mirror.com.
 */

"use strict";

const fs = require("node:fs");
const fsp = require("node:fs/promises");
const path = require("node:path");
const { Readable, Transform } = require("node:stream");
const { pipeline } = require("node:stream/promises");

const ROOT = __dirname;
const MODELS_DIR = path.join(ROOT, "models");
const SVD_DIR = path.join(
  MODELS_DIR,
  "SVD",
  "stable-video-diffusion-img2vid-xt-1-1",
);
const HF_ENDPOINT = (process.env.HF_ENDPOINT || "https://huggingface.co").replace(
  /\/$/,
  "",
);

const ARTIFACTS = [
  {
    relativePath: "DWPose/yolox_l.onnx",
    repo: "yzd-v/DWPose",
    repoPath: "yolox_l.onnx",
    expectedSize: 216_746_733,
  },
  {
    relativePath: "DWPose/dw-ll_ucoco_384.onnx",
    repo: "yzd-v/DWPose",
    repoPath: "dw-ll_ucoco_384.onnx",
    expectedSize: 134_399_116,
  },
  {
    relativePath: "MimicMotion_1-1.pth",
    repo: "tencent/MimicMotion",
    repoPath: "MimicMotion_1-1.pth",
    expectedSize: 3_049_867_447,
  },
  {
    relativePath: "SVD/stable-video-diffusion-img2vid-xt-1-1/model_index.json",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "model_index.json",
    expectedSize: 496,
  },
  {
    relativePath:
      "SVD/stable-video-diffusion-img2vid-xt-1-1/feature_extractor/preprocessor_config.json",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "feature_extractor/preprocessor_config.json",
    expectedSize: 518,
  },
  {
    relativePath:
      "SVD/stable-video-diffusion-img2vid-xt-1-1/image_encoder/config.json",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "image_encoder/config.json",
    expectedSize: 685,
  },
  {
    relativePath:
      "SVD/stable-video-diffusion-img2vid-xt-1-1/image_encoder/model.fp16.safetensors",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "image_encoder/model.fp16.safetensors",
    expectedSize: 1_264_217_240,
  },
  {
    relativePath:
      "SVD/stable-video-diffusion-img2vid-xt-1-1/scheduler/scheduler_config.json",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "scheduler/scheduler_config.json",
    expectedSize: 533,
  },
  {
    relativePath: "SVD/stable-video-diffusion-img2vid-xt-1-1/unet/config.json",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "unet/config.json",
    expectedSize: 984,
  },
  {
    relativePath: "SVD/stable-video-diffusion-img2vid-xt-1-1/vae/config.json",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "vae/config.json",
    expectedSize: 607,
  },
  {
    relativePath:
      "SVD/stable-video-diffusion-img2vid-xt-1-1/vae/diffusion_pytorch_model.fp16.safetensors",
    repo: "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
    repoPath: "vae/diffusion_pytorch_model.fp16.safetensors",
    expectedSize: 195_531_910,
  },
];

function formatBytes(size) {
  let value = size;
  for (const unit of ["B", "KiB", "MiB", "GiB", "TiB"]) {
    if (value < 1024 || unit === "TiB") return `${value.toFixed(2)} ${unit}`;
    value /= 1024;
  }
  throw new Error("Unreachable");
}

function artifactUrl(artifact) {
  const encodedPath = artifact.repoPath
    .split("/")
    .map(encodeURIComponent)
    .join("/");
  return `${HF_ENDPOINT}/${artifact.repo}/resolve/main/${encodedPath}?download=true`;
}

function requestHeaders(offset = 0) {
  const headers = { "User-Agent": "MimicMotion-artifact-downloader/1.0" };
  const token = process.env.HF_TOKEN?.trim();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (offset > 0) headers.Range = `bytes=${offset}-`;
  return headers;
}

class AuthenticationError extends Error {}

async function fetchWithRetries(url, offset, attempts = 10) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: requestHeaders(offset),
        redirect: "follow",
        signal: AbortSignal.timeout(120_000),
      });
      if (response.status === 401 || response.status === 403) {
        throw new AuthenticationError(
          `Hugging Face returned HTTP ${response.status}. Accept the SVD model's ` +
            "access terms in your Hugging Face account, create a read token, and set HF_TOKEN.",
        );
      }
      if (response.status === 416) return response;
      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }
      return response;
    } catch (error) {
      if (error instanceof AuthenticationError) throw error;
      lastError = error;
      if (attempt < attempts) {
        const delay = Math.min(attempt * 5_000, 30_000);
        console.warn(`  Request failed (${error.message}); retrying in ${delay / 1000}s`);
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
  }
  throw lastError;
}

async function downloadArtifact(artifact) {
  const destination = path.join(MODELS_DIR, artifact.relativePath);
  await fsp.mkdir(path.dirname(destination), { recursive: true });

  let currentSize = 0;
  try {
    currentSize = (await fsp.stat(destination)).size;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }

  if (currentSize === artifact.expectedSize) {
    console.log(
      `SKIP ${artifact.relativePath}: already complete (${formatBytes(currentSize)})`,
    );
    return;
  }
  if (currentSize > artifact.expectedSize) {
    console.log(`RESET ${artifact.relativePath}: file is larger than expected`);
    await fsp.rm(destination, { force: true });
    currentSize = 0;
  }

  console.log(
    `${currentSize ? "RESUME" : "DOWNLOAD"} ${artifact.relativePath}` +
      `${currentSize ? ` from ${formatBytes(currentSize)}` : ` (${formatBytes(artifact.expectedSize)})`}`,
  );

  let response = await fetchWithRetries(artifactUrl(artifact), currentSize);
  if (response.status === 416 && currentSize !== artifact.expectedSize) {
    await fsp.rm(destination, { force: true });
    currentSize = 0;
    response = await fetchWithRetries(artifactUrl(artifact), 0);
  }
  if (!response.body) throw new Error(`Empty response body for ${artifact.relativePath}`);

  let downloaded = currentSize;
  let nextReport = downloaded + 128 * 1024 * 1024;
  const progress = new Transform({
    transform(chunk, _encoding, callback) {
      downloaded += chunk.length;
      if (downloaded >= nextReport) {
        console.log(
          `  ${artifact.relativePath}: ${formatBytes(downloaded)} / ` +
            formatBytes(artifact.expectedSize),
        );
        nextReport = downloaded + 128 * 1024 * 1024;
      }
      callback(null, chunk);
    },
  });

  await pipeline(
    Readable.fromWeb(response.body),
    progress,
    fs.createWriteStream(destination, { flags: currentSize ? "a" : "w" }),
  );

  const actualSize = (await fsp.stat(destination)).size;
  if (actualSize !== artifact.expectedSize) {
    throw new Error(
      `Invalid size for ${artifact.relativePath}: expected ${artifact.expectedSize}, ` +
        `got ${actualSize}. Run this script again to resume.`,
    );
  }
  console.log(`OK ${artifact.relativePath}: ${formatBytes(actualSize)}`);
}

async function directorySize(directory) {
  let total = 0;
  for (const entry of await fsp.readdir(directory, { withFileTypes: true })) {
    const item = path.join(directory, entry.name);
    total += entry.isDirectory() ? await directorySize(item) : (await fsp.stat(item)).size;
  }
  return total;
}

async function main() {
  if (Number.parseInt(process.versions.node.split(".")[0], 10) < 20) {
    throw new Error("Node.js 20 or newer is required");
  }
  await fsp.mkdir(SVD_DIR, { recursive: true });
  for (const artifact of ARTIFACTS) await downloadArtifact(artifact);
  const total = await directorySize(MODELS_DIR);
  console.log(`All model downloads completed: ${formatBytes(total)} in ${MODELS_DIR}`);
}

main().catch((error) => {
  console.error(`Download failed: ${error.message}`);
  console.error("Run the script again to resume partial downloads.");
  process.exitCode = 1;
});
