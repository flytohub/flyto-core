// Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.
//
// A tiny, dependency-free Node.js helper for writing a Flyto2 module pack.
//
// registerModule({...}) takes the same fields as Python's @register_module
// (snake_case, same names, same meaning) plus a `handler`. emitManifest()
// prints the flyto.pack.v1 manifest those calls produce -- the same
// language-neutral contract a Python pack's decorators produce. serve() speaks
// the flyto-core subprocess JSON-RPC protocol on stdin/stdout.
//
// Nothing here is Flyto2-specific runtime: the host (flyto-core) validates the
// manifest, verifies the signature, registers the modules and enforces policy.
'use strict';

const readline = require('readline');

const ROW_KEYS = new Set([
  'module_id', 'version', 'stability', 'label', 'label_key', 'description',
  'description_key', 'category', 'subcategory', 'tags', 'icon', 'color',
  'params_schema', 'output_schema', 'input_types', 'output_types',
  'can_receive_from', 'can_connect_to', 'provides_capability', 'contract',
  'required_permissions', 'timeout_ms', 'retryable', 'max_retries',
  'concurrent_safe', 'requires_credentials', 'handles_sensitive_data',
]);

const modules = new Map();
const inFlight = new Set();
let packInfo = null;
let runtimeInfo = null;

function definePack(pack, runtime) {
  packInfo = { ...pack };
  runtimeInfo = { binding: 'subprocess-jsonrpc', language: 'node', entry: 'index.js', ...runtime };
}

function registerModule(spec) {
  const { handler, ...row } = spec;
  if (typeof row.module_id !== 'string' || !row.module_id) {
    throw new Error('registerModule: module_id is required');
  }
  if (typeof handler !== 'function') {
    throw new Error(`registerModule(${row.module_id}): handler must be a function`);
  }
  for (const key of Object.keys(row)) {
    if (!ROW_KEYS.has(key)) {
      throw new Error(`registerModule(${row.module_id}): unknown field '${key}'`);
    }
  }
  if (modules.has(row.module_id)) {
    throw new Error(`registerModule: duplicate module_id '${row.module_id}'`);
  }
  modules.set(row.module_id, { row, handler });
  return handler;
}

function manifest() {
  if (!packInfo) throw new Error('definePack() was not called');
  return {
    schema: 'flyto.pack.v1',
    pack: packInfo,
    runtime: runtimeInfo,
    modules: [...modules.values()].map((m) => m.row),
  };
}

function emitManifest() {
  process.stdout.write(JSON.stringify(manifest(), null, 2) + '\n');
}

function reply(id, result, error) {
  const message = { jsonrpc: '2.0', id };
  if (error) message.error = error; else message.result = result;
  process.stdout.write(JSON.stringify(message) + '\n');
}

async function handle(request) {
  const { id, method, params = {} } = request;
  if (method === 'handshake') {
    return reply(id, { pluginVersion: packInfo.version, protocolVersion: params.protocolVersion });
  }
  if (method === 'ping') return reply(id, {});
  if (method === 'shutdown') {
    // Finish accepted work before exiting; the host drains the same way.
    await Promise.allSettled([...inFlight]);
    reply(id, {});
    process.exit(0);
  }
  if (method !== 'invoke') {
    return reply(id, null, { code: -32601, message: `unknown method ${method}` });
  }
  const entry = modules.get(params.step);
  if (!entry) return reply(id, null, { code: -32001, message: `unknown module ${params.step}` });
  try {
    const data = await entry.handler(params.input || {}, params.context || {});
    // `ok` is always present and always a boolean: absent never means true.
    return reply(id, { ok: true, data });
  } catch (err) {
    return reply(id, { ok: false, error: { code: err.code || 'MODULE_FAILED', message: String(err.message || err) } });
  }
}

function serve() {
  const lines = readline.createInterface({ input: process.stdin });
  lines.on('line', (line) => {
    if (!line.trim()) return;
    let request;
    try {
      request = JSON.parse(line);
    } catch (err) {
      return;
    }
    const task = handle(request);
    if (request.method === 'invoke') {
      inFlight.add(task);
      task.finally(() => inFlight.delete(task));
    }
  });
}

function main() {
  if (process.argv.includes('--manifest')) emitManifest();
  else serve();
}

module.exports = { definePack, registerModule, manifest, emitManifest, serve, main };
