export class BrowserClassifier {
  constructor() {
    this.pending = new Map();
    this.nextId = 0;
    this.worker = new Worker(new URL('./inference-worker.js', import.meta.url), { type: 'module' });
    this.worker.onmessage = ({ data }) => {
      const request = this.pending.get(data.id);
      if (!request) return;
      this.pending.delete(data.id);
      clearTimeout(request.timeout);
      data.error ? request.reject(new Error(data.error)) : request.resolve(data);
    };
    this.worker.onerror = () => this.rejectAll(new Error('浏览器模型未能启动，请重试或使用较新版本的浏览器。'));
  }

  request(type, fields, transfers = []) {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      const timeout = setTimeout(() => { this.pending.delete(id); reject(new Error(type === 'load' ? '模型下载较慢，请检查网络后重试。' : '分析超时，请重新加载模型后重试。')); }, type === 'load' ? 180000 : 60000);
      this.pending.set(id, { resolve, reject, timeout });
      this.worker.postMessage({ id, type, ...fields }, transfers);
    });
  }

  async load(config) { this.config = config; await this.request('load', { config }); }

  async predict(file, monsters) {
    const input = await preprocess(file, this.config.preprocessing);
    const { logits } = await this.request('predict', { input }, [input.buffer]);
    if (logits.length !== this.config.classes.length || ![...logits].every(Number.isFinite)) throw new Error('模型输出异常，请重新加载。');
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

  dispose() { this.rejectAll(new Error('模型已重新加载。')); this.worker.terminate(); }
}

async function preprocess(file, config) {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  try {
    if (bitmap.width * bitmap.height > 20000000) throw new Error('图片不能超过 2000 万像素。');
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
