import * as ort from './vendor/ort.wasm.min.mjs';

let session;
ort.env.wasm.numThreads = 1;
ort.env.wasm.wasmPaths = new URL('./vendor/', import.meta.url).href;

self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'load') {
      const response = await fetch(new URL(data.config.modelFile, import.meta.url));
      if (!response.ok) throw new Error('模型文件下载失败，请重试。');
      const buffer = await response.arrayBuffer();
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))].map(v => v.toString(16).padStart(2, '0')).join('');
      if (hash !== data.config.sha256) throw new Error('模型文件不完整，请刷新重试。');
      session = await ort.InferenceSession.create(buffer, { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
      self.postMessage({ id: data.id, ready: true });
    } else if (data.type === 'predict') {
      if (!session) throw new Error('模型还在准备中。');
      const tensor = new ort.Tensor('float32', data.input, [1, 3, 224, 224]);
      const output = await session.run({ image: tensor });
      const logits = Float32Array.from(output.logits.data);
      self.postMessage({ id: data.id, logits }, [logits.buffer]);
    }
  } catch (error) {
    self.postMessage({ id: data.id, error: error.message || '模型运行失败，请重新加载。' });
  }
};
