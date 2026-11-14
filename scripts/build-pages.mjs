import { cp, lstat, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { gzipSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

await import('./copy-runtime.mjs');
const root = fileURLToPath(new URL('../', import.meta.url));
const web = path.join(root, 'web');
const dist = path.resolve(root, 'dist');
if (path.relative(root, dist) !== 'dist') throw new Error('Invalid build destination.');
const previous = await lstat(dist).catch(error => { if (error.code !== 'ENOENT') throw error; });
if (previous?.isSymbolicLink()) throw new Error('Build destination cannot be a symbolic link.');
await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(web, dist, { recursive: true });
await writeFile(path.join(dist, '.nojekyll'), '');

const model = JSON.parse(await readFile(path.join(dist, 'data', 'model.json'), 'utf8'));
const monsters = JSON.parse(await readFile(path.join(dist, 'data', 'catalog.json'), 'utf8'));
const keys = new Set(monsters.map(monster => monster.id));
if (keys.size !== 30 || model.classes.length !== keys.size || model.classes.some(key => !keys.has(key))) throw new Error('Class catalog mismatch.');
const bytes = await readFile(path.join(dist, model.modelFile));
if (createHash('sha256').update(bytes).digest('hex') !== model.sha256) throw new Error('Model checksum mismatch. Run export_browser.py.');
const mobileGraph = JSON.parse(await readFile(path.join(web, 'data/mobile-graph.json'), 'utf8'));
if (mobileGraph.sha256 !== model.sha256) throw Error('Run scripts/export-mobile.py for the new model.');
model.mobileParts = [];
for (let offset = 0; offset < bytes.length; offset += 512 * 1024) {
  const part = `models/${model.sha256.slice(0,12)}-${model.mobileParts.length}.bin`;
  await writeFile(path.join(dist, part), bytes.subarray(offset, offset + 512 * 1024));
  model.mobileParts.push(part);
}
model.compressedModelFile = `${model.modelFile}.gz`;
await writeFile(path.join(dist, model.compressedModelFile), gzipSync(bytes, { level: 9 }));
await writeFile(path.join(dist, 'data', 'model.json'), JSON.stringify(model));
for (const monster of monsters) await stat(path.join(dist, 'portraits', `${monster.id}.jpg`));
const html = await readFile(path.join(dist, 'index.html'), 'utf8');
if (/\b(?:src|href)=["']\/(?!\/)/.test(html)) throw new Error('Root-absolute asset path is incompatible with project Pages.');
const appVersion = createHash('sha256').update(await readFile(path.join(dist, 'app.js'))).digest('hex').slice(0, 12);
await writeFile(path.join(dist, 'index.html'), html.replace('src="./app.js"', `src="./app.js?v=${appVersion}"`));
let total = 0;
async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) await inspect(filename);
    else { const size = (await stat(filename)).size; if (size >= 100 * 1024 * 1024) throw new Error('Asset exceeds GitHub file limit.'); total += size; }
  }
}
await inspect(dist);
console.log(`Built GitHub Pages artifact: 30 classes, ${(total / 1024 / 1024).toFixed(1)} MiB. All paths are relative.`);
