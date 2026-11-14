export class BrowserClassifier {
  constructor() {
    this.pending = new Map();
    this.nextId = 0;
  }
  startWorker(mobile) {
    this.worker = new Worker(new URL(mobile ? './mobile-worker.js' : './inference-worker.js', import.meta.url), { type: 'module' });
    this.worker.onmessage = ({ data }) => {
      const request = this.pending.get(data.id);
      if (!request) return;
      if (data.progress) {
        clearTimeout(request.timeout);
        request.timeout = setTimeout(request.expire, request.duration);
        this.onProgress?.(data.progress);
        return;
      }
      this.pending.delete(data.id);
      clearTimeout(request.timeout);
      data.error ? request.reject(new Error(data.error)) : request.resolve(data);
    };
    this.worker.onerror = () => this.rejectAll(new Error('errorWorker'));
  }

  request(type, fields, transfers = []) {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      const duration = type === 'load' ? 180000 : 60000;
      const expire = () => { this.pending.delete(id); reject(new Error(type === 'load' ? 'errorDownloadTimeout' : 'errorPredictTimeout')); };
      const timeout = setTimeout(expire, duration);
      this.pending.set(id, { resolve, reject, timeout, expire, duration });
      this.worker.postMessage({ id, type, ...fields }, transfers);
    });
  }

  async load(config, onProgress) {
    this.config = config;
    this.onProgress = onProgress;
    const mobile = navigator.maxTouchPoints > 0 || /Android|iPhone|iPad/i.test(navigator.userAgent);
    if (!mobile) {
      try {
        this.startWorker(false);
        await this.request('load', {config});
        return;
      } catch { this.worker?.terminate(); }
    }
    this.startWorker(true);
    await this.request('load', {config});
  }

  async predict(file, monsters) {
    const input = await preprocess(file, this.config.preprocessing);
    const { logits } = await this.request('predict', { input }, [input.buffer]);
    if (logits.length !== this.config.classes.length || ![...logits].every(Number.isFinite)) throw new Error('errorOutput');
    const max = Math.max(...logits);
    const weights = Array.from(logits, value => Math.exp(value - max));
    const total = weights.reduce((a, b) => a + b, 0);
    const byId = new Map(monsters.map(m => [m.id, m]));
    const ranking = this.config.classes.map((key, i) => ({ monster: byId.get(key), score: weights[i] / total })).sort((a, b) => b.score - a.score);
    return { winner: ranking[0].monster, ranking, mode: 'model', notice: this.config.notice };
  }

  rejectAll(error) {
    for (const { reject, timeout } of this.pending.values()) { clearTimeout(timeout); reject(error); }
    this.pending.clear();
  }

  dispose() { this.rejectAll(new Error('errorReload')); this.worker?.terminate(); }
}

async function preprocess(file, config) {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  try {
    if (bitmap.width * bitmap.height > 20000000) throw new Error('errorPixels');
    const ratio = config.resize / Math.min(bitmap.width, bitmap.height);
    const width = Math.floor(bitmap.width * ratio), height = Math.floor(bitmap.height * ratio);
    const resized = document.createElement('canvas'); resized.width = width; resized.height = height;
    const context = resized.getContext('2d');
    context.fillStyle = '#fff'; context.fillRect(0, 0, width, height);
    context.imageSmoothingEnabled = true; context.imageSmoothingQuality = 'high';
    context.drawImage(bitmap, 0, 0, width, height);
    const size = config.crop;
    const crop = document.createElement('canvas'); crop.width = size; crop.height = size;
    const cropContext = crop.getContext('2d');
    cropContext.drawImage(resized, Math.round((width - size) / 2), Math.round((height - size) / 2), size, size, 0, 0, size, size);
    const rgba = cropContext.getImageData(0, 0, size, size).data;
    const plane = size * size, input = new Float32Array(plane * 3);
    for (let channel = 0; channel < 3; channel++) {
      for (let i = 0; i < plane; i++) input[channel * plane + i] = (rgba[i * 4 + channel] / 255 - config.mean[channel]) / config.std[channel];
    }
    return input;
  } finally { bitmap.close(); }
}
