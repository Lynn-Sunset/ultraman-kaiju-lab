// Download compressed assets where supported; retain the original for older browsers.
export async function loadBinary(url, { compressedUrl, onProgress = () => {}, signal } = {}) {
  const compressed = compressedUrl && typeof DecompressionStream === 'function';
  const response = await fetch(compressed ? compressedUrl : url, { signal });
  if (!response.ok) {
    if (compressed && response.status === 404) return loadBinary(url, { onProgress, signal });
    throw new Error('模型资源下载失败，请检查网络后重新加载。');
  }
  const total = Number(response.headers.get('content-length'));
  let received = 0;
  const stream = response.body?.pipeThrough && typeof TransformStream === 'function' ? response.body.pipeThrough(new TransformStream({
    transform(chunk, controller) {
      received += chunk.byteLength;
      onProgress({ received, total });
      controller.enqueue(chunk);
    },
  })) : undefined;
  // Detect gzip by its bytes as some hosts already decode Content-Encoding: gzip.
  const bytes = new Uint8Array(await (stream ? new Response(stream) : response).arrayBuffer());
  if (!stream) onProgress({ received: bytes.byteLength, total });
  if (compressed && bytes[0] === 0x1f && bytes[1] === 0x8b) {
    try {
      return await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    } catch {
      return loadBinary(url, { onProgress, signal });
    }
  }
  return bytes.buffer;
}
