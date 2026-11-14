import * as ort from './vendor/ort.wasm.bundle.min.mjs';
import { loadBinary } from './model-assets.js';

let session;
ort.env.wasm.numThreads = 1;
ort.env.wasm.wasmPaths = { wasm: new URL('./vendor/ort-wasm-simd-threaded.wasm', import.meta.url).href };

self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'load') {
      const controller = new AbortController();
      const received = { model: 0, runtime: 0 };
      let lastUpdate = 0;
      const progress = key => ({ received: bytes }) => {
        received[key] = bytes;
        if (performance.now() - lastUpdate < 150) return;
        lastUpdate = performance.now();
        self.postMessage({ id: data.id, progress: { mb: (received.model + received.runtime) / 1024 / 1024 } });
      };
      const modelUrl = new URL(data.config.modelFile, import.meta.url);
      modelUrl.searchParams.set('v', data.config.sha256);
      const compressedModelUrl = data.config.compressedModelFile ? new URL(data.config.compressedModelFile, import.meta.url) : undefined;
      compressedModelUrl?.searchParams.set('v', data.config.sha256);
      const runtimeUrl = new URL('./vendor/ort-wasm-simd-threaded.wasm?v=1.31.1', import.meta.url);
      let buffer, wasm;
      try {
        [buffer, wasm] = await Promise.all([
          loadBinary(modelUrl, { compressedUrl: compressedModelUrl, onProgress: progress('model'), signal: controller.signal }),
          loadBinary(runtimeUrl, { compressedUrl: new URL('./vendor/ort-wasm-simd-threaded.wasm.gz?v=1.31.1', import.meta.url), onProgress: progress('runtime'), signal: controller.signal }),
        ]);
      } catch (error) { controller.abort(); throw error; }
      self.postMessage({ id: data.id, progress: { phase: 'starting' } });
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', buffer))].map(v => v.toString(16).padStart(2, '0')).join('');
      if (hash !== data.config.sha256) throw new Error('errorChecksum');
      ort.env.wasm.wasmBinary = wasm;
      session = await ort.InferenceSession.create(buffer, { executionProviders: ['wasm'], graphOptimizationLevel: 'all' });
      self.postMessage({ id: data.id, ready: true });
    } else if (data.type === 'predict') {
      if (!session) throw new Error('errorModelNotReady');
      const tensor = new ort.Tensor('float32', data.input, [1, 3, 224, 224]);
      const output = await session.run({ image: tensor });
      const logits = Float32Array.from(output.logits.data);
      self.postMessage({ id: data.id, logits }, [logits.buffer]);
    }
  } catch (error) {
    self.postMessage({ id: data.id, error: error.message || 'errorModel' });
  }
};
