#!/usr/bin/env node
/**
 * Check the Runpod Network Volume (S3 API) and upload only the missing artifacts.
 *
 * Usage from the repository root with Node.js 20+:
 *   node upload_models.js            Check remote state, then upload what is missing.
 *   node upload_models.js --check    Report remote state only; upload nothing.
 *
 * Required environment variables (a root .env file is also read):
 *   RUNPOD_S3_ENDPOINT
 *   RUNPOD_S3_REGION
 *   RUNPOD_S3_ACCESS_KEY
 *   RUNPOD_S3_SECRET_KEY
 *   RUNPOD_NETWORK_VOLUME_ID
 *
 * No npm packages are required: requests are signed with AWS Signature V4
 * using Node's built-in crypto module.
 */

"use strict";

const crypto = require("node:crypto");
const fsp = require("node:fs/promises");
const path = require("node:path");

const ROOT = __dirname;
const MODELS_DIR = path.join(ROOT, "models");
const ENV_FILE = path.join(ROOT, ".env");
const READY_KEY = "ARTIFACTS_READY";
const KEY_PREFIX = "models";

const REQUIRED_ENV = [
  "RUNPOD_S3_ENDPOINT",
  "RUNPOD_S3_REGION",
  "RUNPOD_S3_ACCESS_KEY",
  "RUNPOD_S3_SECRET_KEY",
  "RUNPOD_NETWORK_VOLUME_ID",
];

/** Artifacts the worker needs, with the exact upstream sizes. */
const EXPECTED_ARTIFACTS = new Map([
  ["DWPose/yolox_l.onnx", 216_746_733],
  ["DWPose/dw-ll_ucoco_384.onnx", 134_399_116],
  ["MimicMotion_1-1.pth", 3_049_867_447],
  ["SVD/stable-video-diffusion-img2vid-xt-1-1/model_index.json", 496],
  [
    "SVD/stable-video-diffusion-img2vid-xt-1-1/feature_extractor/preprocessor_config.json",
    518,
  ],
  ["SVD/stable-video-diffusion-img2vid-xt-1-1/image_encoder/config.json", 685],
  [
    "SVD/stable-video-diffusion-img2vid-xt-1-1/image_encoder/model.fp16.safetensors",
    1_264_217_240,
  ],
  ["SVD/stable-video-diffusion-img2vid-xt-1-1/scheduler/scheduler_config.json", 533],
  ["SVD/stable-video-diffusion-img2vid-xt-1-1/unet/config.json", 984],
  ["SVD/stable-video-diffusion-img2vid-xt-1-1/vae/config.json", 607],
  [
    "SVD/stable-video-diffusion-img2vid-xt-1-1/vae/diffusion_pytorch_model.fp16.safetensors",
    195_531_910,
  ],
]);

const SKIP_PATTERNS = [/(^|\/)\.cache(\/|$)/, /\.lock$/, /\.metadata$/, /(^|\/)\.DS_Store$/];

const MULTIPART_THRESHOLD = 64 * 1024 * 1024;
const PART_SIZE = 64 * 1024 * 1024;
const MAX_ATTEMPTS = 5;

function formatBytes(size) {
  let value = size;
  for (const unit of ["B", "KiB", "MiB", "GiB", "TiB"]) {
    if (value < 1024 || unit === "TiB") return `${value.toFixed(2)} ${unit}`;
    value /= 1024;
  }
  throw new Error("Unreachable");
}

async function loadDotEnv(file) {
  let content;
  try {
    content = await fsp.readFile(file, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const separator = line.indexOf("=");
    const name = line.slice(0, separator).trim();
    let value = line.slice(separator + 1).trim();
    if (value.length >= 2 && value[0] === value[value.length - 1] && /["']/.test(value[0])) {
      value = value.slice(1, -1);
    }
    if (name && process.env[name] === undefined) process.env[name] = value;
  }
}

function readConfig() {
  const missing = REQUIRED_ENV.filter((name) => !process.env[name]?.trim());
  if (missing.length > 0) {
    throw new Error(
      `Missing environment variables: ${missing.join(", ")}. ` +
        "Set them in the shell or in a root .env file.",
    );
  }
  const endpoint = new URL(process.env.RUNPOD_S3_ENDPOINT.trim());
  return {
    endpoint,
    region: process.env.RUNPOD_S3_REGION.trim(),
    accessKey: process.env.RUNPOD_S3_ACCESS_KEY.trim(),
    secretKey: process.env.RUNPOD_S3_SECRET_KEY.trim(),
    bucket: process.env.RUNPOD_NETWORK_VOLUME_ID.trim(),
  };
}

function sha256Hex(payload) {
  return crypto.createHash("sha256").update(payload).digest("hex");
}

function hmac(key, value) {
  return crypto.createHmac("sha256", key).update(value).digest();
}

function encodeSegment(segment) {
  return encodeURIComponent(segment).replace(/[!'()*]/g, (c) =>
    `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
  );
}

function canonicalQuery(query) {
  return Object.keys(query)
    .sort()
    .map((name) => `${encodeSegment(name)}=${encodeSegment(String(query[name]))}`)
    .join("&");
}

/** Sign and send one S3 request using AWS Signature V4. */
async function signedRequest(config, options) {
  const { method, key, query = {}, body, payloadHash, timeoutMs = 300_000 } = options;
  const canonicalPath =
    "/" +
    [config.bucket, ...key.split("/")]
      .filter((segment) => segment.length > 0)
      .map(encodeSegment)
      .join("/");

  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const dateStamp = amzDate.slice(0, 8);
  const hashedPayload = payloadHash ?? (body ? sha256Hex(body) : sha256Hex(""));

  const headers = {
    host: config.endpoint.host,
    "x-amz-content-sha256": hashedPayload,
    "x-amz-date": amzDate,
  };
  const signedHeaderNames = Object.keys(headers).sort();
  const canonicalHeaders = signedHeaderNames.map((n) => `${n}:${headers[n]}\n`).join("");
  const signedHeaders = signedHeaderNames.join(";");

  const canonicalRequest = [
    method,
    canonicalPath,
    canonicalQuery(query),
    canonicalHeaders,
    signedHeaders,
    hashedPayload,
  ].join("\n");

  const scope = `${dateStamp}/${config.region}/s3/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    scope,
    sha256Hex(canonicalRequest),
  ].join("\n");

  let signingKey = hmac(`AWS4${config.secretKey}`, dateStamp);
  for (const part of [config.region, "s3", "aws4_request"]) {
    signingKey = hmac(signingKey, part);
  }
  const signature = crypto.createHmac("sha256", signingKey).update(stringToSign).digest("hex");

  headers.authorization =
    `AWS4-HMAC-SHA256 Credential=${config.accessKey}/${scope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;

  const search = canonicalQuery(query);
  const url = `${config.endpoint.origin}${canonicalPath}${search ? `?${search}` : ""}`;

  return fetch(url, {
    method,
    headers,
    body,
    signal: AbortSignal.timeout(timeoutMs),
  });
}

async function requestWithRetries(config, options, label) {
  let lastError;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      const response = await signedRequest(config, options);
      if (response.status === 403) {
        const detail = await response.text();
        throw new Error(
          `Access denied (HTTP 403) for ${label}. Check the Runpod S3 credentials, ` +
            `region, and network volume ID. ${detail.slice(0, 200)}`,
        );
      }
      if (response.status >= 500 || response.status === 429) {
        throw new Error(`HTTP ${response.status} for ${label}`);
      }
      return response;
    } catch (error) {
      lastError = error;
      if (String(error.message).includes("HTTP 403")) throw error;
      if (attempt < MAX_ATTEMPTS) {
        const delay = Math.min(attempt * 4_000, 20_000);
        console.warn(`  Retry ${attempt}/${MAX_ATTEMPTS - 1} for ${label}: ${error.message}`);
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
  }
  throw lastError;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Size reported by HEAD, or null when the object is absent or unreported. */
async function headSize(config, key) {
  const response = await requestWithRetries(
    config,
    { method: "HEAD", key, timeoutMs: 60_000 },
    `HEAD ${key}`,
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`HEAD ${key} failed: HTTP ${response.status}`);
  const length = response.headers.get("content-length");
  return length === null ? null : Number.parseInt(length, 10);
}

/** Size from a bucket listing; the volume gateway reports writes here first. */
async function listSize(config, key) {
  const response = await requestWithRetries(
    config,
    {
      method: "GET",
      key: "",
      query: { "list-type": "2", prefix: key, "max-keys": "1000" },
      timeoutMs: 120_000,
    },
    `LIST ${key}`,
  );
  if (!response.ok) return null;
  const xml = await response.text();
  const blocks = xml.matchAll(/<Contents>([\s\S]*?)<\/Contents>/g);
  for (const [, block] of blocks) {
    if (xmlValue(block, "Key") !== key) continue;
    const size = xmlValue(block, "Size");
    return size === null ? null : Number.parseInt(size, 10);
  }
  return null;
}

/** Return the remote object size, or null when the object is absent. */
async function remoteSize(config, key) {
  const head = await headSize(config, key);
  if (head !== null) return head;
  return listSize(config, key);
}

/** Poll until the remote size matches, tolerating write-visibility delay. */
async function awaitRemoteSize(config, key, expected, attempts = 8) {
  let observed = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    observed = await remoteSize(config, key);
    if (observed === expected) return observed;
    if (attempt < attempts) await sleep(Math.min(attempt * 2_000, 10_000));
  }
  return observed;
}

async function putObject(config, key, body) {
  const response = await requestWithRetries(
    config,
    { method: "PUT", key, body, timeoutMs: 600_000 },
    `PUT ${key}`,
  );
  if (!response.ok) {
    throw new Error(`PUT ${key} failed: HTTP ${response.status} ${await response.text()}`);
  }
}

function xmlValue(xml, tag) {
  const match = xml.match(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`));
  return match ? match[1] : null;
}

function escapeXml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

async function abortMultipart(config, key, uploadId) {
  await signedRequest(config, {
    method: "DELETE",
    key,
    query: { uploadId },
    timeoutMs: 60_000,
  }).catch(() => undefined);
}

/** Read the server-authoritative part ETags before completing an upload. */
async function listMultipartParts(config, key, uploadId, expectedCount) {
  const response = await requestWithRetries(
    config,
    {
      method: "GET",
      key,
      query: { uploadId, "max-parts": "1000" },
      timeoutMs: 120_000,
    },
    `LIST PARTS ${key}`,
  );
  const xml = await response.text();
  if (!response.ok) {
    throw new Error(`ListParts failed for ${key}: HTTP ${response.status} ${xml.slice(0, 300)}`);
  }

  const parts = [];
  for (const match of xml.matchAll(/<Part>([\s\S]*?)<\/Part>/g)) {
    const partNumber = Number.parseInt(xmlValue(match[1], "PartNumber"), 10);
    const etag = xmlValue(match[1], "ETag");
    if (Number.isInteger(partNumber) && etag) parts.push({ partNumber, etag });
  }
  parts.sort((a, b) => a.partNumber - b.partNumber);
  if (parts.length !== expectedCount) {
    throw new Error(
      `Runpod reports ${parts.length} parts for ${key}; expected ${expectedCount}`,
    );
  }
  return parts;
}

/** Upload one large file as a sequence of signed multipart requests. */
async function multipartUpload(config, key, filePath, size) {
  const initiate = await requestWithRetries(
    config,
    { method: "POST", key, query: { uploads: "" }, timeoutMs: 120_000 },
    `CREATE ${key}`,
  );
  const initiateBody = await initiate.text();
  if (!initiate.ok) {
    throw new Error(`Multipart start failed for ${key}: HTTP ${initiate.status} ${initiateBody}`);
  }
  const uploadId = xmlValue(initiateBody, "UploadId");
  if (!uploadId) throw new Error(`Missing UploadId for ${key}`);

  const totalParts = Math.ceil(size / PART_SIZE);
  const responseEtags = [];
  const handle = await fsp.open(filePath, "r");

  try {
    for (let partNumber = 1; partNumber <= totalParts; partNumber += 1) {
      const offset = (partNumber - 1) * PART_SIZE;
      const length = Math.min(PART_SIZE, size - offset);
      const buffer = Buffer.allocUnsafe(length);
      await handle.read(buffer, 0, length, offset);

      const response = await requestWithRetries(
        config,
        {
          method: "PUT",
          key,
          query: { partNumber: String(partNumber), uploadId },
          body: buffer,
          payloadHash: sha256Hex(buffer),
          timeoutMs: 900_000,
        },
        `PART ${partNumber}/${totalParts} of ${key}`,
      );
      if (!response.ok) {
        throw new Error(
          `Part ${partNumber} failed for ${key}: HTTP ${response.status} ${await response.text()}`,
        );
      }
      const etag = response.headers.get("etag");
      if (!etag) throw new Error(`Missing ETag for part ${partNumber} of ${key}`);
      responseEtags.push({ partNumber, etag });
      console.log(
        `    part ${partNumber}/${totalParts} uploaded ` +
          `(${formatBytes(Math.min(offset + length, size))} / ${formatBytes(size)})`,
      );
    }
  } catch (error) {
    await abortMultipart(config, key, uploadId);
    throw error;
  } finally {
    await handle.close();
  }

  // Runpod's S3 gateway may return a transformed ETag in UploadPart responses.
  // ListParts is the authoritative source accepted by CompleteMultipartUpload.
  let parts;
  try {
    parts = await listMultipartParts(config, key, uploadId, totalParts);
  } catch (error) {
    await abortMultipart(config, key, uploadId);
    throw error;
  }

  for (const part of parts) {
    const responsePart = responseEtags.find((candidate) => candidate.partNumber === part.partNumber);
    if (responsePart && responsePart.etag !== part.etag) {
      console.log(`    using server ETag for part ${part.partNumber}`);
    }
  }

  const completeBody =
    "<CompleteMultipartUpload>" +
    parts
      .map(
        (p) =>
          `<Part><PartNumber>${p.partNumber}</PartNumber><ETag>${escapeXml(p.etag)}</ETag></Part>`,
      )
      .join("") +
    "</CompleteMultipartUpload>";

  const complete = await requestWithRetries(
    config,
    {
      method: "POST",
      key,
      query: { uploadId },
      body: Buffer.from(completeBody, "utf8"),
      timeoutMs: 600_000,
    },
    `COMPLETE ${key}`,
  );
  const completeText = await complete.text();
  if (!complete.ok || completeText.includes("<Error>")) {
    await abortMultipart(config, key, uploadId);
    throw new Error(`Multipart completion failed for ${key}: ${completeText.slice(0, 300)}`);
  }
}

async function collectLocalFiles(directory) {
  const files = [];
  async function walk(current) {
    for (const entry of await fsp.readdir(current, { withFileTypes: true })) {
      const absolute = path.join(current, entry.name);
      const relative = path.relative(MODELS_DIR, absolute).split(path.sep).join("/");
      if (SKIP_PATTERNS.some((pattern) => pattern.test(relative))) continue;
      if (entry.isDirectory()) {
        await walk(absolute);
      } else if (entry.isFile()) {
        files.push({ relative, absolute, size: (await fsp.stat(absolute)).size });
      }
    }
  }
  await walk(directory);
  return files.sort((a, b) => a.relative.localeCompare(b.relative));
}

function validateLocalFiles(files) {
  const byPath = new Map(files.map((file) => [file.relative, file]));
  const problems = [];
  for (const [relative, expectedSize] of EXPECTED_ARTIFACTS) {
    const file = byPath.get(relative);
    if (!file) {
      problems.push(`missing: models/${relative}`);
    } else if (file.size !== expectedSize) {
      problems.push(`size mismatch: models/${relative} (expected ${expectedSize}, got ${file.size})`);
    }
  }
  if (problems.length > 0) {
    throw new Error(
      `Local artifacts are incomplete:\n  ${problems.join("\n  ")}\n` +
        "Run node download_models.js again before uploading.",
    );
  }
}

async function main() {
  if (Number.parseInt(process.versions.node.split(".")[0], 10) < 20) {
    throw new Error("Node.js 20 or newer is required");
  }
  const checkOnly = process.argv.includes("--check") || process.argv.includes("--dry-run");

  await loadDotEnv(ENV_FILE);
  const config = readConfig();

  try {
    await fsp.access(MODELS_DIR);
  } catch {
    throw new Error(`Models directory not found: ${MODELS_DIR}`);
  }

  const files = await collectLocalFiles(MODELS_DIR);
  if (files.length === 0) throw new Error("No files found under models/");
  validateLocalFiles(files);
  console.log(`Local artifacts verified: ${files.length} files`);
  console.log(`Remote target: bucket ${config.bucket} at ${config.endpoint.origin}\n`);

  const missing = [];
  for (const file of files) {
    const key = `${KEY_PREFIX}/${file.relative}`;
    const size = await remoteSize(config, key);
    if (size === file.size) {
      console.log(`PRESENT ${key} (${formatBytes(file.size)})`);
    } else if (size === null) {
      console.log(`MISSING ${key} (${formatBytes(file.size)})`);
      missing.push({ ...file, key, reason: "missing" });
    } else {
      console.log(`INCOMPLETE ${key} (remote ${formatBytes(size)}, local ${formatBytes(file.size)})`);
      missing.push({ ...file, key, reason: "size mismatch" });
    }
  }

  const markerPresent = (await remoteSize(config, READY_KEY)) !== null;
  console.log(`\n${missing.length} file(s) need upload; marker ${READY_KEY}: ${markerPresent ? "present" : "absent"}`);

  if (checkOnly) {
    console.log("Check-only mode: nothing was uploaded.");
    return;
  }

  for (const [index, file] of missing.entries()) {
    console.log(
      `\n[${index + 1}/${missing.length}] UPLOAD ${file.key} ` +
        `(${formatBytes(file.size)}, ${file.reason})`,
    );
    if (file.size >= MULTIPART_THRESHOLD) {
      await multipartUpload(config, file.key, file.absolute, file.size);
    } else {
      await putObject(config, file.key, await fsp.readFile(file.absolute));
    }
    const uploaded = await awaitRemoteSize(config, file.key, file.size);
    if (uploaded !== file.size) {
      throw new Error(
        `Verification failed for ${file.key}: local ${file.size}, remote ${uploaded}`,
      );
    }
    console.log(`  OK ${file.key}`);
  }

  const failures = [];
  for (const file of files) {
    const key = `${KEY_PREFIX}/${file.relative}`;
    const size = await awaitRemoteSize(config, key, file.size);
    if (size !== file.size) failures.push(`${key} (local ${file.size}, remote ${size})`);
  }
  if (failures.length > 0) {
    throw new Error(`Remote verification failed for:\n  ${failures.join("\n  ")}`);
  }

  await putObject(config, READY_KEY, Buffer.alloc(0));
  const total = files.reduce((sum, file) => sum + file.size, 0);
  console.log(
    `\nAll ${files.length} artifacts present on the volume (${formatBytes(total)}). ` +
      `Marker ${READY_KEY} written.`,
  );
}

main().catch((error) => {
  console.error(`\nUpload failed: ${error.message}`);
  console.error("Fix the issue and run the script again; existing files are skipped.");
  process.exitCode = 1;
});
