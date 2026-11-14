import { BrowserClassifier } from './inference.js';
import { renderIdentityCard } from './identity-card.js';
import { applyTranslations, detectLocale, getLocale, localizeMonster, locales, setLocale, t } from './i18n.js';

const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
let monsters = [], config, classifier, modelReady = false, busy = false, selectedFile, previewURL, currentResult, selectionId = 0;
let modelState = 'modelLoading', resultState = 'unrevealed', errorKey = '', toastKey = '', dialogState, archiveState = 'loading', rankingExpanded = false, saving = false;
const input = $('#photo-input'), dropzone = $('#dropzone'), classifyButton = $('#classify-button');
let storage;
try { storage = window.localStorage; } catch { /* Storage may be disabled. */ }
setLocale(detectLocale(storage, navigator.languages || [navigator.language]));

async function getJSON(path) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(new URL(path, import.meta.url), { signal: controller.signal });
    if (!response.ok) throw new Error('errorFiles');
    return await response.json();
  } finally { clearTimeout(timeout); }
}
function knownError(error, fallback) { return /^error[A-Z]/.test(error?.message) ? error.message : fallback; }
function showError(key = '') { errorKey = key; $('#upload-error').textContent = key ? t(key) : ''; $('#upload-error').hidden = !key; }
function toast(key) {
  toastKey = key; $('#toast').textContent = t(key); $('#toast').hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { $('#toast').hidden = true; toastKey = ''; }, 4000);
}
function updateButton() {
  classifyButton.disabled = !modelReady || !selectedFile || busy;
  classifyButton.firstElementChild.textContent = t(busy ? 'matching' : modelReady ? 'reveal' : 'modelLoading');
}
let downloadedMB = null;
function renderModelState() {
  $('#model-state').textContent = t(modelState, { count: config?.classes.length || 30 }) +
    (modelState === 'modelLoading' && downloadedMB !== null ? ' ' + downloadedMB.toLocaleString(getLocale(), { maximumFractionDigits: 1 }) + ' MB' : '');
  updateButton();
}

async function initializeModel() {
  if (busy) return;
  modelReady = false; downloadedMB = null; modelState = 'modelLoading'; $('#retry-model').hidden = true; showError(); renderModelState();
  try {
    classifier?.dispose(); classifier = new BrowserClassifier();
    await classifier.load(config, progress => { downloadedMB = progress.mb ?? null; renderModelState(); });
    modelReady = true; modelState = 'modelReady';
  } catch (error) {
    classifier?.dispose(); classifier = undefined;
    modelState = 'modelFailed'; $('#retry-model').hidden = false;
    showError(knownError(error, 'errorModel'));
  }
  renderModelState();
}

function renderArchive() {
  $('#hero-count').textContent = t('heroCount', { count: monsters.length || 30 });
  if (archiveState !== 'ready') {
    $('#archive-grid').innerHTML = `<p class="${archiveState === 'failed' ? 'error' : 'muted'}">${t(archiveState === 'failed' ? 'archiveFailed' : 'archiveLoading')}</p>`;
    return;
  }
  const query = $('#archive-search').value.normalize('NFKC').trim().toLocaleLowerCase();
  const era = $('#archive-era').value;
  const filtered = monsters.filter(monster => (!era || monster.era === era) &&
    [monster.name, monster.en, monster.jp, ...locales.flatMap(language => { const profile = localizeMonster(monster, language); return [profile.name, profile.title]; })]
      .some(value => value.normalize('NFKC').toLocaleLowerCase().includes(query)));
  $('#archive-results').textContent = t('archiveCount', { count: filtered.length, total: monsters.length });
  $('#archive-grid').innerHTML = filtered.length ? filtered.map(original => {
    const monster = localizeMonster(original);
    return `<button class="monster-card" data-monster="${monster.id}" aria-label="${escapeHTML(t('viewMonster', { name: monster.name }))}"><div class="card-photo"><span class="card-number">${String(monsters.indexOf(original) + 1).padStart(2, '0')}</span><img src="./portraits/${monster.id}.jpg" alt="${escapeHTML(monster.name)}" loading="lazy"></div><div class="card-text"><h3>${escapeHTML(monster.name)}<span>↗</span></h3><span class="card-type">${escapeHTML(monster.title)}</span></div></button>`;
  }).join('') : `<p class="archive-empty">${t('archiveEmpty')}</p>`;
}

function renderDialog() {
  if (!dialogState) return;
  if (dialogState === 'about') {
    $('#dialog-content').innerHTML = `<h2 class="dialog-title" id="dialog-title">${t('aboutTitle')}</h2><p class="dialog-copy">${t('aboutPrivacy')}</p><p class="dialog-copy">${t('aboutDownload')}</p><a class="dialog-source" href="https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages#data-collection" target="_blank" rel="noopener noreferrer">${t('aboutHost')}</a>`;
    return;
  }
  const monster = localizeMonster(dialogState);
  $('#dialog-content').innerHTML = `<h2 class="dialog-title" id="dialog-title">${escapeHTML(monster.name)}</h2><p class="dialog-copy">${escapeHTML(monster.title)} · ${escapeHTML(monster.debut)}</p><img class="dialog-photo" src="./portraits/${monster.id}.jpg" alt="${escapeHTML(monster.name)}"><div class="dialog-specs"><span>${escapeHTML(monster.en)}</span><span>${escapeHTML(t('height', { height: monster.height }))}</span></div><div class="result-abilities">${monster.abilities.map(ability => `<span>${escapeHTML(ability)}</span>`).join('')}</div><p class="dialog-copy">${escapeHTML(monster.description)}</p><a class="dialog-source" href="${monster.source}" target="_blank" rel="noopener noreferrer">${t('officialProfile')}</a>`;
}
function openDialog(content) { dialogState = content; renderDialog(); $('#info-dialog').showModal(); }

function renderPhotoInfo() {
  $('#file-info').innerHTML = selectedFile ? `<span>${escapeHTML(selectedFile.name)} · ${new Intl.NumberFormat(getLocale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(selectedFile.size / 1024 / 1024)} MB</span><button id="remove-photo" aria-label="${t('removePhoto')}">${t('remove')}</button>` : `<span>${t('photoHint')}</span>`;
  if (selectedFile) $('#remove-photo').onclick = resetPhoto;
}
async function selectFile(file) {
  if (busy || !file) return;
  const requestId = ++selectionId;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return showError('errorFormat');
  if (!file.size || file.size > 10 * 1024 * 1024) return showError('errorSize');
  const url = URL.createObjectURL(file);
  const valid = await new Promise(resolve => { const image = new Image(); image.onload = () => resolve(image.naturalWidth * image.naturalHeight <= 20000000); image.onerror = () => resolve(false); image.src = url; });
  if (requestId !== selectionId) { URL.revokeObjectURL(url); return; }
  if (!valid) { URL.revokeObjectURL(url); return showError('errorImage'); }
  if (previewURL) URL.revokeObjectURL(previewURL);
  previewURL = url; selectedFile = file; currentResult = null; resultState = 'awaiting';
  $('#photo-preview').src = url; $('#photo-preview').hidden = false; $('#dropzone-empty').hidden = true; $('.photo-change').hidden = false;
  renderPhotoInfo(); renderResult(); showError(); updateButton();
}
function resetPhoto() {
  if (busy) return;
  selectionId++;
  if (previewURL) URL.revokeObjectURL(previewURL);
  selectedFile = undefined; previewURL = undefined; currentResult = undefined; input.value = ''; resultState = 'unrevealed';
  $('#photo-preview').removeAttribute('src'); $('#photo-preview').hidden = true; $('#dropzone-empty').hidden = false; $('.photo-change').hidden = true;
  renderPhotoInfo(); renderResult(); showError(); updateButton();
}

function renderResult(result) {
  if (result) { currentResult = result; resultState = result.mode === 'demo' ? 'demoStatus' : 'complete'; rankingExpanded = false; }
  $('#result-status').textContent = t(resultState);
  if (resultState === 'matchingStatus') {
    $('#result-content').innerHTML = `<div class="loading-result"><div class="loading-spinner"></div><p>${t('finding')}</p></div>`;
    return;
  }
  if (!currentResult) {
    $('#result-content').innerHTML = `<div class="empty-result"><span class="empty-symbol" aria-hidden="true">✳</span><h3>${t('emptyTitle')}</h3><p>${t('emptyCopy')}</p></div>`;
    return;
  }
  const monster = localizeMonster(currentResult.winner);
  $('#result-content').innerHTML = `${currentResult.mode === 'demo' ? `<p class="demo-note">${t('demoNote')}</p>` : ''}<div class="winner-header"><div class="winner-portrait"><img src="./portraits/${monster.id}.jpg" alt="${escapeHTML(monster.name)}"></div><div class="winner-intro"><span>${t('identity')}</span><h3>${escapeHTML(t('youAre', { name: monster.name }))}</h3><p>${escapeHTML(monster.title)}</p></div></div><div class="result-abilities">${monster.abilities.map(ability => `<span>${escapeHTML(ability)}</span>`).join('')}</div><p class="winner-description">${escapeHTML(monster.description)}</p><div class="rank-label"><span>${t('ranking')}</span><span>${t('relativeScore')}</span></div><div class="ranking-list">${currentResult.ranking.map((row, index) => `<div class="rank-row"${index >= 5 && !rankingExpanded ? ' hidden' : ''}><span>${escapeHTML(localizeMonster(row.monster).name)}</span><div class="rank-track"><span style="width:${(row.score * 100).toFixed(3)}%"></span></div><span>${new Intl.NumberFormat(getLocale(), { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(row.score)}</span></div>`).join('')}</div>${currentResult.ranking.length > 5 ? `<button class="text-button ranking-toggle" aria-expanded="${rankingExpanded}">${t(rankingExpanded ? 'collapseRanking' : 'expandRanking', { count: currentResult.ranking.length })}</button>` : ''}<div class="result-actions"><button class="secondary" id="save-card"${saving ? ' disabled' : ''}>${t(saving ? 'generating' : 'saveCard')}</button></div>`;
  const toggle = $('.ranking-toggle');
  if (toggle) toggle.onclick = () => {
    rankingExpanded = !rankingExpanded; toggle.setAttribute('aria-expanded', String(rankingExpanded));
    [...document.querySelectorAll('.rank-row')].slice(5).forEach(row => row.hidden = !rankingExpanded);
    toggle.textContent = t(rankingExpanded ? 'collapseRanking' : 'expandRanking', { count: currentResult.ranking.length });
  };
  $('#save-card').onclick = saveCard;
}

async function classify() {
  if (!selectedFile || !modelReady || busy) return;
  showError(); busy = true; currentResult = null; resultState = 'matchingStatus'; updateButton(); $('#demo-button').disabled = true; dropzone.disabled = true; $('#retry-model').disabled = true; renderResult();
  try {
    renderResult(await classifier.predict(selectedFile, monsters));
    if (innerWidth < 701) $('#result-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    showError(knownError(error, 'errorMatch')); resultState = 'retryStatus'; renderResult();
  } finally { busy = false; $('#demo-button').disabled = false; dropzone.disabled = false; $('#retry-model').disabled = false; updateButton(); }
}
function demo() {
  if (!monsters.length || busy) return;
  const weights = monsters.map((_, index) => Math.exp(-index / 1.7));
  const total = weights.reduce((a, b) => a + b, 0);
  renderResult({ winner: monsters[0], ranking: monsters.map((monster, index) => ({ monster, score: weights[index] / total })), mode: 'demo' });
  if (innerWidth < 701) $('#result-panel').scrollIntoView({ behavior: 'smooth' });
}
async function saveCard() {
  if (!currentResult || saving) return;
  const result = currentResult, language = getLocale(); saving = true; renderResult();
  try {
    const blob = await renderIdentityCard(result, language);
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = `KAIJU-LAB-${result.winner.id}-${language}${result.mode === 'demo' ? '-demo' : ''}.png`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast('cardSaved');
  } catch { toast('errorCard'); }
  finally { saving = false; renderResult(); }
}
function renderPage() {
  applyTranslations(); $('#language-select').value = getLocale();
  const gomora = monsters.find(monster => monster.id === 'gomora');
  if (gomora) {
    const localized = localizeMonster(gomora);
    $('.hero-art > img').alt = `${localized.title} ${localized.name}`;
    $('.hero-caption').innerHTML = `${escapeHTML(localized.name)} <small>${escapeHTML(localized.title)}</small>`;
  }
  renderModelState(); renderPhotoInfo(); renderArchive(); renderResult(); renderDialog(); showError(errorKey);
  if (toastKey) $('#toast').textContent = t(toastKey);
}

$('#language-select').addEventListener('change', event => { setLocale(event.target.value, storage); renderPage(); });
$('#about-button').onclick = () => openDialog('about');
$('#close-dialog').onclick = () => $('#info-dialog').close();
$('#info-dialog').addEventListener('close', () => { dialogState = undefined; });
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
$('#archive-grid').addEventListener('click', event => { const card = event.target.closest('[data-monster]'); if (card) openDialog(monsters.find(monster => monster.id === card.dataset.monster)); });

renderPage();
try {
  [monsters, config] = await Promise.all([getJSON('./data/catalog.json'), getJSON('./data/model.json')]);
  const keys = new Set(monsters.map(monster => monster.id));
  if (config.classes.length !== keys.size || config.classes.some(key => !keys.has(key))) throw new Error('errorCatalog');
  archiveState = 'ready'; renderPage(); await initializeModel();
} catch (error) {
  archiveState = 'failed'; modelState = 'loadFailed'; renderPage(); showError(knownError(error, 'errorFiles'));
}
