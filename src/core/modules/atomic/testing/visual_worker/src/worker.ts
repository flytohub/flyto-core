#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";

const REQUEST_SCHEMA = "flyto.visual.compare.request.v1";
const RESULT_SCHEMA = "flyto.visual.compare.result.v1";
const MAX_REQUEST_BYTES = 64 * 1024;
const MAX_IMAGE_BYTES = 50 * 1024 * 1024;
const MAX_PIXELS = 64 * 1024 * 1024;

type CompareRequest = {
  schema: typeof REQUEST_SCHEMA;
  expectedPath: string;
  actualPath: string;
  diffPath?: string;
  mismatchThreshold?: number;
  colorThreshold?: number;
  includeAntiAliased?: boolean;
};

type LoadedImage = {
  path: string;
  bytes: Buffer;
  png: PNG;
  sha256: string;
};

function sha256(value: Buffer | string): string {
  return createHash("sha256").update(value).digest("hex");
}

function requireRatio(value: unknown, name: string, fallback: number): number {
  const ratio = value === undefined ? fallback : value;
  if (typeof ratio !== "number" || !Number.isFinite(ratio) || ratio < 0 || ratio > 1) {
    throw new Error(`${name} must be a finite number between 0 and 1`);
  }
  return ratio;
}

function requirePath(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${name} must be a non-empty local file path`);
  }
  if (/^https?:\/\//i.test(value) || value.startsWith("data:")) {
    throw new Error(`${name} must be a local file path; URLs and data URIs are not accepted`);
  }
  return path.resolve(value);
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    if (size > MAX_REQUEST_BYTES) {
      throw new Error(`request exceeds ${MAX_REQUEST_BYTES}-byte limit`);
    }
    chunks.push(bytes);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function loadPng(inputPath: string, name: string): Promise<LoadedImage> {
  const filePath = requirePath(inputPath, name);
  const fileStat = await stat(filePath);
  if (!fileStat.isFile()) {
    throw new Error(`${name} is not a regular file`);
  }
  if (fileStat.size > MAX_IMAGE_BYTES) {
    throw new Error(`${name} exceeds ${MAX_IMAGE_BYTES}-byte limit`);
  }

  const bytes = await readFile(filePath);
  validatePngHeader(bytes, name);
  let png: PNG;
  try {
    png = PNG.sync.read(bytes, { checkCRC: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`${name} is not a valid PNG: ${message}`);
  }

  const pixels = png.width * png.height;
  if (!Number.isSafeInteger(pixels) || pixels <= 0 || pixels > MAX_PIXELS) {
    throw new Error(`${name} dimensions exceed the ${MAX_PIXELS}-pixel limit`);
  }
  return { path: filePath, bytes, png, sha256: sha256(bytes) };
}

function validatePngHeader(bytes: Buffer, name: string): void {
  const signature = "89504e470d0a1a0a";
  if (
    bytes.length < 24
    || bytes.subarray(0, 8).toString("hex") !== signature
    || bytes.readUInt32BE(8) !== 13
    || bytes.subarray(12, 16).toString("ascii") !== "IHDR"
  ) {
    throw new Error(`${name} is not a valid PNG header`);
  }
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  const pixels = width * height;
  if (!Number.isSafeInteger(pixels) || width === 0 || height === 0 || pixels > MAX_PIXELS) {
    throw new Error(`${name} dimensions exceed the ${MAX_PIXELS}-pixel limit`);
  }
}

function align(image: PNG, width: number, height: number): Buffer {
  const output = Buffer.alloc(width * height * 4);
  const source = Buffer.from(image.data);
  for (let y = 0; y < image.height; y += 1) {
    const sourceStart = y * image.width * 4;
    const targetStart = y * width * 4;
    source.copy(output, targetStart, sourceStart, sourceStart + image.width * 4);
  }
  return output;
}

async function compare(request: CompareRequest) {
  if (!request || request.schema !== REQUEST_SCHEMA) {
    throw new Error(`schema must be ${REQUEST_SCHEMA}`);
  }

  const mismatchThreshold = requireRatio(request.mismatchThreshold, "mismatchThreshold", 0.001);
  const colorThreshold = requireRatio(request.colorThreshold, "colorThreshold", 0.1);
  const [expected, actual] = await Promise.all([
    loadPng(request.expectedPath, "expectedPath"),
    loadPng(request.actualPath, "actualPath"),
  ]);

  const width = Math.max(expected.png.width, actual.png.width);
  const height = Math.max(expected.png.height, actual.png.height);
  const totalPixels = width * height;
  if (totalPixels > MAX_PIXELS) {
    throw new Error(`aligned dimensions exceed the ${MAX_PIXELS}-pixel limit`);
  }

  const expectedPixels = align(expected.png, width, height);
  const actualPixels = align(actual.png, width, height);
  const diffPixelsBuffer = Buffer.alloc(totalPixels * 4);
  const startedAt = process.hrtime.bigint();
  const differentPixels = pixelmatch(
    expectedPixels,
    actualPixels,
    diffPixelsBuffer,
    width,
    height,
    {
      threshold: colorThreshold,
      includeAA: request.includeAntiAliased === true,
      alpha: 0.15,
      diffColor: [239, 68, 68],
      aaColor: [245, 158, 11],
    },
  );
  const elapsedMs = Number(process.hrtime.bigint() - startedAt) / 1_000_000;
  const differenceRatio = differentPixels / totalPixels;
  const diffImage = new PNG({ width, height });
  diffImage.data = diffPixelsBuffer;
  const diffBytes = PNG.sync.write(diffImage);

  let diffPath: string | null = null;
  if (request.diffPath !== undefined) {
    diffPath = requirePath(request.diffPath, "diffPath");
    if (path.extname(diffPath).toLowerCase() !== ".png") {
      throw new Error("diffPath must end in .png");
    }
    if (diffPath === expected.path || diffPath === actual.path) {
      throw new Error("diffPath must not overwrite an input image");
    }
    await mkdir(path.dirname(diffPath), { recursive: true });
    await writeFile(diffPath, diffBytes, { flag: "wx" });
  }

  const dimensionMatch = expected.png.width === actual.png.width && expected.png.height === actual.png.height;
  const runId = sha256([
    expected.sha256,
    actual.sha256,
    String(mismatchThreshold),
    String(colorThreshold),
    String(request.includeAntiAliased === true),
  ].join(":"));

  return {
    schema: RESULT_SCHEMA,
    ok: true,
    runId,
    match: differenceRatio <= mismatchThreshold,
    differenceRatio,
    differencePercent: differenceRatio * 100,
    differentPixels,
    totalPixels,
    mismatchThreshold,
    colorThreshold,
    dimensionMatch,
    dimensions: {
      expected: { width: expected.png.width, height: expected.png.height },
      actual: { width: actual.png.width, height: actual.png.height },
      compared: { width, height },
    },
    algorithm: "pixelmatch@7.2.0",
    elapsedMs,
    diffPath,
    evidence: {
      expectedSha256: expected.sha256,
      actualSha256: actual.sha256,
      diffSha256: sha256(diffBytes),
    },
  };
}

async function main(): Promise<void> {
  try {
    const raw = await readStdin();
    const request = JSON.parse(raw) as CompareRequest;
    const result = await compare(request);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stdout.write(`${JSON.stringify({ schema: RESULT_SCHEMA, ok: false, error: message })}\n`);
  }
}

await main();
