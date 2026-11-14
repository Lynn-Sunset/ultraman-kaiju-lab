import { messages } from './locales/messages.js';
import { profiles, series } from './locales/profiles.js';

export const locales = ['zh-CN', 'ja', 'en', 'es', 'ru'];
export const storageKey = 'kaiju-lab-language';
export function resolveLocale(value) {
  const language = String(value || '').toLowerCase().split(/[-_]/)[0];
  return language === 'zh' ? 'zh-CN' : locales.find(locale => locale === language);
}
export function detectLocale(storage, languages = []) {
  try {
    const saved = resolveLocale(storage?.getItem(storageKey));
    if (saved) return saved;
  } catch { /* Private browsing can disable storage. */ }
  return languages.map(resolveLocale).find(Boolean) || 'zh-CN';
}
let locale = 'zh-CN';
export const getLocale = () => locale;
export function setLocale(value, storage) {
  locale = resolveLocale(value) || 'zh-CN';
  try { storage?.setItem(storageKey, locale); } catch { /* Switching still works without storage. */ }
  return locale;
}
export function translate(language, key, values = {}) {
  const template = messages[language]?.[key] ?? messages['zh-CN'][key];
  if (template === undefined) throw new Error(`Missing translation: ${key}`);
  return template.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? `{${name}}`));
}
export const t = (key, values) => translate(locale, key, values);
export function localizeMonster(monster, language = locale) {
  if (language === 'zh-CN') return monster;
  const profile = profiles[language]?.[monster.id];
  if (!profile) return monster;
  const [title, abilities, description, russianName] = profile;
  return { ...monster, name: language === 'ja' ? monster.jp : language === 'ru' ? russianName : monster.en,
    title, abilities: abilities.split('|'), description, debut: series[monster.debut]?.[language] || monster.debut };
}
export function applyTranslations(root = document) {
  root.documentElement.lang = locale;
  root.title = t('pageTitle');
  root.querySelector('meta[name="description"]').content = t('metaDescription');
  for (const element of root.querySelectorAll('[data-i18n]')) element.textContent = t(element.dataset.i18n);
  for (const attribute of ['aria-label', 'placeholder', 'alt']) {
    for (const element of root.querySelectorAll(`[data-i18n-${attribute}]`)) element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
  }
}
