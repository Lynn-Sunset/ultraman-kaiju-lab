import { test } from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { loadBinary } from '../web/model-assets.js';

test('compressed downloads, progress, plain fallback, and HTTP errors', async t => {
  const original = Buffer.from('model data '.repeat(1024));
  const compressed = gzipSync(original);
  const hits = [];
  const server = createServer((request, response) => {
    hits.push(request.url);
    if (request.url === '/missing') { response.writeHead(404).end(); return; }
    if (request.url === '/error') { response.writeHead(500).end(); return; }
    const bytes = request.url === '/compressed' || request.url === '/encoded' ? compressed : original;
    response.setHeader('Content-Length', bytes.length);
    if (request.url === '/encoded') response.setHeader('Content-Encoding', 'gzip');
    response.end(bytes);
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => { server.closeAllConnections(); server.close(); });
  const url = path => `http://127.0.0.1:${server.address().port}${path}`;

  let progress;
  const bytes = await loadBinary(url('/raw'), { compressedUrl: url('/compressed'), onProgress: value => { progress = value; } });
  assert.deepEqual(Buffer.from(bytes), original);
  assert.equal(progress.received, compressed.length);
  assert.equal(progress.total, compressed.length);
  assert.deepEqual(hits, ['/compressed']);

  assert.deepEqual(Buffer.from(await loadBinary(url('/raw'), { compressedUrl: url('/missing') })), original);
  assert.deepEqual(hits.slice(-2), ['/missing', '/raw']);
  assert.deepEqual(Buffer.from(await loadBinary(url('/raw'), { compressedUrl: url('/encoded') })), original);
  await assert.rejects(loadBinary(url('/raw'), { compressedUrl: url('/error') }), /下载失败/);

  const decompressor = globalThis.DecompressionStream;
  try {
    globalThis.DecompressionStream = undefined;
    assert.deepEqual(Buffer.from(await loadBinary(url('/raw'), { compressedUrl: url('/compressed') })), original);
    assert.equal(hits.at(-1), '/raw');
  } finally { globalThis.DecompressionStream = decompressor; }
});
