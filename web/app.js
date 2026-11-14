import { BrowserClassifier } from './inference.js';
import { renderIdentityCard } from './identity-card.js';

const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
let monsters = [], config, classifier, modelReady = false, busy = false, selectedFile, previewURL, currentResult, selectionId = 0;
const emptyResult = $('#result-content').innerHTML;
const input = $('#photo-input'), dropzone = $('#dropzone'), classifyButton = $('#classify-button');

async function getJSON(path) {
  const response = await fetch(new URL(path, import.meta.url), { signal: AbortSignal.timeout(20000) });
  if (!response.ok) throw new Error('文件加载失败，请检查网络后刷新。');
  return response.json();
}

function showError(message = '') { $('#upload-error').textContent = message; $('#upload-error').hidden = !message; }
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => $('#toast').hidden = true, 4000); }
function updateButton() {
  classifyButton.disabled = !modelReady || !selectedFile || busy;
  classifyButton.firstElementChild.textContent = busy ? '正在匹配…' : modelReady ? '揭晓我的怪兽' : '准备模型中…';
}

async function initializeModel() {
  modelReady = false; $('#retry-model').hidden = true; $('#model-state').textContent = '正在准备模型…'; updateButton();
  classifier?.dispose(); classifier = new BrowserClassifier();
  try {
    await classifier.load(config);
    modelReady = true; $('#model-state').textContent = `${config.classes.length} 类怪兽已就绪`;
  } catch (error) {
    $('#model-state').textContent = '模型未能加载'; $('#retry-model').hidden = false;
    showError(error.message);
  }
  updateButton();
}

function renderArchive() {
  const query = $('#archive-search').value.normalize('NFKC').trim().toLocaleLowerCase();
  const era = $('#archive-era').value;
  const filtered = monsters.filter(monster => (!era || monster.era === era) && [monster.name, monster.en, monster.jp, monster.title].some(value => value.normalize('NFKC').toLocaleLowerCase().includes(query)));
  $('#archive-count').textContent = monsters.length;
  $('#archive-results').textContent = `${filtered.length} / ${monsters.length} 位`;
  $('#archive-grid').innerHTML = filtered.length ? filtered.map(monster => `<button class="monster-card" data-monster="${monster.id}" aria-label="查看${escapeHTML(monster.name)}的能力档案"><div class="card-photo"><span class="card-number">${String(monsters.indexOf(monster) + 1).padStart(2, '0')}</span><img src="./portraits/${monster.id}.jpg" alt="${escapeHTML(monster.name)}" loading="lazy"></div><div class="card-text"><h3>${escapeHTML(monster.name)}<span>↗</span></h3><span class="card-type">${escapeHTML(monster.title)}</span></div></button>`).join('') : '<p class="archive-empty">没有找到，试试其他名字或系列。</p>';
}

function openDialog(html) { $('#dialog-content').innerHTML = html; $('#info-dialog').showModal(); }
function showMonster(monster) {
  openDialog(`<h2 class="dialog-title">${escapeHTML(monster.name)}</h2><p class="dialog-copy">${escapeHTML(monster.title)} · ${escapeHTML(monster.debut)}</p><img class="dialog-photo" src="./portraits/${monster.id}.jpg" alt="${escapeHTML(monster.name)}"><div class="dialog-specs"><span>${escapeHTML(monster.en)}</span><span>身高 ${escapeHTML(monster.height)}</span></div><div class="result-abilities">${monster.abilities.map(ability => `<span>${escapeHTML(ability)}</span>`).join('')}</div><p class="dialog-copy">${escapeHTML(monster.description)}</p><a class="dialog-source" href="${monster.source}" target="_blank" rel="noopener noreferrer">圆谷官方档案 ↗</a>`);
}

async function selectFile(file) {
  if (busy || !file) return;
  const requestId = ++selectionId;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return showError('请选择 JPG、PNG 或 WebP 图片。');
  if (!file.size || file.size > 10 * 1024 * 1024) return showError('请选择非空且不超过 10 MB 的图片。');
  const url = URL.createObjectURL(file);
  const valid = await new Promise(resolve => { const image = new Image(); image.onload = () => resolve(image.naturalWidth * image.naturalHeight <= 20000000); image.onerror = () => resolve(false); image.src = url; });
  if (requestId !== selectionId) { URL.revokeObjectURL(url); return; }
  if (!valid) { URL.revokeObjectURL(url); return showError('图片无法读取，或超过 2000 万像素。'); }
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = url; selectedFile = file; currentResult = null;
  $('#photo-preview').src = url; $('#photo-preview').hidden = false; $('#dropzone-empty').hidden = true; $('.photo-change').hidden = false;
  $('#file-info').innerHTML = `<span>${escapeHTML(file.name)} · ${(file.size / 1024 / 1024).toFixed(2)} MB</span><button id="remove-photo" aria-label="移除已选照片">移除 ×</button>`;
  $('#remove-photo').onclick = resetPhoto;
  $('#result-content').innerHTML = emptyResult; $('#result-status').textContent = '待匹配'; showError(); updateButton();
}

function resetPhoto() {
  if (busy) return;
  selectionId++;
  if (previewURL) URL.revokeObjectURL(previewURL);
  selectedFile = undefined; previewURL = undefined; currentResult = undefined; input.value = '';
  $('#photo-preview').removeAttribute('src'); $('#photo-preview').hidden = true; $('#dropzone-empty').hidden = false; $('.photo-change').hidden = true;
  $('#file-info').innerHTML = '<span>建议使用主体清晰的单人照片</span>';
  $('#result-content').innerHTML = emptyResult; $('#result-status').textContent = '待揭晓'; showError(); updateButton();
}

function renderResult(result) {
  currentResult = result;
  const monster = result.winner;
  $('#result-status').textContent = result.mode === 'demo' ? '示例' : '匹配完成';
  $('#result-content').innerHTML = `${result.mode === 'demo' ? '<p class="demo-note">预设示例，与上传照片无关。</p>' : ''}<div class="winner-header"><div class="winner-portrait"><img src="./portraits/${monster.id}.jpg" alt="${escapeHTML(monster.name)}"></div><div class="winner-intro"><span>你的怪兽身份</span><h3>你是${escapeHTML(monster.name)}</h3><p>${escapeHTML(monster.title)}</p></div></div><div class="result-abilities">${monster.abilities.map(ability => `<span>${escapeHTML(ability)}</span>`).join('')}</div><p class="winner-description">${escapeHTML(monster.description)}</p><div class="rank-label"><span>匹配排名</span><span>相对类别得分</span></div><div class="ranking-list">${result.ranking.map((row, index) => `<div class="rank-row"${index >= 5 ? ' hidden' : ''}><span>${escapeHTML(row.monster.name)}</span><div class="rank-track"><span style="width:${(row.score * 100).toFixed(3)}%"></span></div><span>${(row.score * 100).toFixed(1)}%</span></div>`).join('')}</div>${result.ranking.length > 5 ? `<button class="text-button ranking-toggle" aria-expanded="false">查看全部 ${result.ranking.length} 类 ↓</button>` : ''}<div class="result-actions"><button class="secondary" id="save-card">↓ 保存身份卡</button></div>`;
  const toggle = $('.ranking-toggle');
  if (toggle) toggle.onclick = () => {
    const expand = toggle.getAttribute('aria-expanded') !== 'true'; toggle.setAttribute('aria-expanded', String(expand));
    [...document.querySelectorAll('.rank-row')].slice(5).forEach(row => row.hidden = !expand);
    toggle.textContent = expand ? '收起排名 ↑' : `查看全部 ${result.ranking.length} 类 ↓`;
  };
  $('#save-card').onclick = saveCard;
}

async function classify() {
  if (!selectedFile || !modelReady || busy) return;
  showError(); busy = true; updateButton(); $('#demo-button').disabled = true; dropzone.disabled = true;
  $('#result-status').textContent = '匹配中'; $('#result-content').innerHTML = '<div class="loading-result"><div class="loading-spinner"></div><p>正在寻找你的怪兽身份…</p></div>';
  try {
    renderResult(await classifier.predict(selectedFile, monsters));
    if (innerWidth < 701) $('#result-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    showError(error.message || '匹配失败，请重试。'); $('#result-content').innerHTML = emptyResult; $('#result-status').textContent = '可重试';
  } finally { busy = false; $('#demo-button').disabled = false; dropzone.disabled = false; updateButton(); }
}

function demo() {
  if (!monsters.length || busy) return;
  const weights = monsters.map((_, index) => Math.exp(-index / 1.7));
  const total = weights.reduce((a, b) => a + b, 0);
  renderResult({ winner: monsters[0], ranking: monsters.map((monster, index) => ({ monster, score: weights[index] / total })), mode: 'demo' });
  if (innerWidth < 701) $('#result-panel').scrollIntoView({ behavior: 'smooth' });
}

async function saveCard() {
  if (!currentResult) return;
  const result = currentResult, button = $('#save-card'); button.disabled = true; button.textContent = '正在生成…';
  try {
    const blob = await renderIdentityCard(result);
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = `KAIJU-LAB-${result.winner.id}${result.mode === 'demo' ? '-demo' : ''}.png`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast('身份卡已生成');
  } catch (error) { toast(error.message || '生成失败，请稍后重试。'); }
  finally { button.disabled = false; button.textContent = '↓ 保存身份卡'; }
}

$('#about-button').onclick = () => {
  openDialog(`<h2 class="dialog-title">隐私与数据安全</h2><p class="dialog-copy">照片和匹配结果仅在你的浏览器中处理，本站不会上传、保存或用于模型训练。</p><p class="dialog-copy">只有你主动保存身份卡时，才会生成文件并下载到本机。</p><a class="dialog-source" href="https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages#data-collection" target="_blank" rel="noopener noreferrer">托管方 GitHub 会为安全目的记录访问 IP ↗</a>`);
};
$('#close-dialog').onclick = () => $('#info-dialog').close();
$('#info-dialog').addEventListener('click', event => {
  if (event.target !== $('#info-dialog')) return;
  const rect = event.target.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close();
});
dropzone.onclick = () => { input.value = ''; input.click(); };
input.onchange = () => selectFile(input.files[0]);
for (const name of ['dragenter', 'dragover']) dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add('dragging'); });
for (const name of ['dragleave', 'drop']) dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove('dragging'); });
dropzone.addEventListener('drop', event => selectFile(event.dataTransfer.files[0]));
window.addEventListener('dragover', event => event.preventDefault()); window.addEventListener('drop', event => event.preventDefault());
classifyButton.onclick = classify; $('#demo-button').onclick = demo; $('#retry-model').onclick = initializeModel;
$('#archive-search').addEventListener('input', renderArchive); $('#archive-era').addEventListener('change', renderArchive);
$('#archive-grid').addEventListener('click', event => { const card = event.target.closest('[data-monster]'); if (card) showMonster(monsters.find(monster => monster.id === card.dataset.monster)); });

try {
  [monsters, config] = await Promise.all([getJSON('./data/catalog.json'), getJSON('./data/model.json')]);
  const keys = new Set(monsters.map(monster => monster.id));
  if (config.classes.length !== keys.size || config.classes.some(key => !keys.has(key))) throw new Error('模型类别与图鉴不一致，请刷新后重试。');
  renderArchive(); await initializeModel();
} catch (error) {
  $('#archive-grid').innerHTML = '<p class="error">图鉴加载失败，请检查网络后刷新。</p>';
  $('#model-state').textContent = '加载失败'; showError(error.message);
}
