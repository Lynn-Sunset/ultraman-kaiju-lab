// Exercise the production worker with the real compressed ONNX and WASM files.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('compressed production assets initialize and produce 30 finite logits', async t => {
  const originalFetch = globalThis.fetch;
  const originalSelf = globalThis.self;
  const messages = [];
  globalThis.self = { postMessage: message => messages.push(message) };
  globalThis.fetch = async (input, options) => {
    const url = new URL(input);
    if (url.protocol !== 'file:') return originalFetch(input, options);
    const bytes = await readFile(url);
    return new Response(bytes, { headers: { 'Content-Length': String(bytes.length) } });
  };
  t.after(() => { globalThis.fetch = originalFetch; globalThis.self = originalSelf; });
  const config = JSON.parse(await readFile(new URL('../dist/data/model.json', import.meta.url), 'utf8'));
  await import('../dist/inference-worker.js');
  await self.onmessage({ data: { id: 1, type: 'load', config } });
  assert.equal(messages.at(-1).error, undefined);
  assert.equal(messages.at(-1).ready, true);
  assert.ok(messages.some(message => message.progress?.includes('正在启动模型')));
  await self.onmessage({ data: { id: 2, type: 'predict', input: new Float32Array(3 * 224 * 224) } });
  const result = messages.at(-1);
  assert.equal(result.error, undefined);
  assert.equal(result.logits.length, 30);
  assert.ok([...result.logits].every(Number.isFinite));
  await self.onmessage({ data: { id: 3, type: 'load', config: { ...config, sha256: 'invalid' } } });
  assert.match(messages.at(-1).error, /模型文件不完整/);
});
