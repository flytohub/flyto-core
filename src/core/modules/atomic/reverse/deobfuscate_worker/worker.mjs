#!/usr/bin/env node
// Single-shot deobfuscation worker: reads exactly one JSON line from stdin,
// writes exactly one JSON line to stdout, exits. No handshake/ping/shutdown
// protocol — one process per invocation, spawned and killed by the caller
// (core.modules.atomic.reverse.deobfuscate).

import { webcrack } from 'webcrack';

const MAX_INPUT_BYTES = 5 * 1024 * 1024; // 5MB, mirrors the Python module's cap

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    process.stdin.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_INPUT_BYTES) {
        reject(new Error(`Input exceeds ${MAX_INPUT_BYTES} byte limit`));
        process.stdin.destroy();
        return;
      }
      chunks.push(chunk);
    });
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    process.stdin.on('error', reject);
  });
}

async function main() {
  let request;
  try {
    const raw = await readStdin();
    request = JSON.parse(raw);
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: `Invalid request: ${err.message}` }) + '\n');
    process.exitCode = 0;
    return;
  }

  const source = request && request.source;
  if (typeof source !== 'string' || source.length === 0) {
    process.stdout.write(JSON.stringify({ ok: false, error: 'Missing or empty "source" field' }) + '\n');
    return;
  }

  try {
    const result = await webcrack(source);
    process.stdout.write(JSON.stringify({
      ok: true,
      code: result.code,
      bundleDetected: Boolean(result.bundle),
    }) + '\n');
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: err && err.message ? err.message : String(err) }) + '\n');
  }
}

main();
