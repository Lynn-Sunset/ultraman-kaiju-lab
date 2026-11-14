import { copyFile, mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const runtime = path.join(root, 'node_modules', 'onnxruntime-web');
const metadata = JSON.parse(await readFile(path.join(runtime, 'package.json'), 'utf8'));
if (metadata.version !== '1.31.1') throw new Error('Unexpected ONNX Runtime version. Run npm ci.');
const target = path.join(root, 'web', 'vendor');
await mkdir(target, { recursive: true });
for (const file of ['ort.wasm.min.mjs', 'ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.wasm']) {
  await copyFile(path.join(runtime, 'dist', file), path.join(target, file));
}
await copyFile(path.join(root, 'third_party', 'onnxruntime-LICENSE.txt'), path.join(target, 'LICENSE-onnxruntime.txt'));
console.log('Prepared ONNX Runtime Web 1.31.1 (single-threaded WASM).');
