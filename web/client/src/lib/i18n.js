// Ilova tili: o'zbekcha (asosiy), ruscha, inglizcha.
// Kalit — o'zbekcha matnning o'zi: t("Bosh sahifa") → «Главная». Tarjimasi yo'q matn o'zbekcha qoladi,
// shuning uchun yangi ekranlarni bosqichma-bosqich tarjima qilish xavfsiz.
// Tanlov qurilmada (localStorage) va Telegram bulutida saqlanadi — boshqa qurilmada ham shu til ochiladi.
import { useSyncExternalStore } from 'react';

import DICT from './i18n-dict.js';
import { tg } from './telegram.js';

const KEY = 'slayd-lang';
const COLUMN = { ru: 0, en: 1 };

/** Tanlash oynasidagi tartib. sub — til nomi joriy til bilan (t orqali). */
export const LANGS = [
  { code: 'uz', name: "O'zbekcha", sub: "O'zbek tili", region: "O'zbekiston" },
  { code: 'ru', name: 'Русский', sub: 'Rus tili', region: 'Rossiya' },
  { code: 'en', name: 'English', sub: 'Ingliz tili', region: 'Buyuk Britaniya' },
];

const listeners = new Set();
let current = 'uz';

const valid = (code) => LANGS.some((l) => l.code === code);

function readLocal() {
  try {
    const value = localStorage.getItem(KEY);
    return valid(value) ? value : null;
  } catch {
    return null;
  }
}

function apply(code) {
  current = code;
  document.documentElement.lang = code;
  listeners.forEach((listener) => listener());
}

/** Birinchi ochilishda: saqlangan tanlov, bo'lmasa — Telegram tili (ru / en), aks holda o'zbekcha. */
export function initLang() {
  const telegram = tg?.initDataUnsafe?.user?.language_code;
  const guess = telegram === 'ru' || telegram === 'en' ? telegram : 'uz';
  apply(readLocal() ?? guess);
  if (tg?.CloudStorage && tg.isVersionAtLeast?.('6.9')) {
    tg.CloudStorage.getItem(KEY, (error, value) => {
      if (!error && valid(value) && value !== current) {
        apply(value);
        try { localStorage.setItem(KEY, value); } catch { /* e'tiborsiz */ }
      }
    });
  }
}

export function setLang(code) {
  if (!valid(code) || code === current) return;
  apply(code);
  try { localStorage.setItem(KEY, code); } catch { /* e'tiborsiz */ }
  if (tg?.CloudStorage && tg.isVersionAtLeast?.('6.9')) tg.CloudStorage.setItem(KEY, code, () => {});
}

export const getLang = () => current;

/** Tarjima. vars: t('{n} ta dizayn', { n: 5 }).
 *  Kontekst: bir xil o'zbekcha so'z ikki ma'noda bo'lsa — t('Kirish#qism') («Введение»), t('Kirish') («Войти»).
 *  «#» dan keyingi qism faqat lug'at kaliti uchun, ekranda ko'rinmaydi. */
export function t(text, vars) {
  if (typeof text !== 'string') return text ?? '';
  const hash = text.indexOf('#');
  const base = hash > 0 ? text.slice(0, hash) : text;
  let out = base;
  if (current !== 'uz' && text) out = DICT[text]?.[COLUMN[current]] ?? DICT[base]?.[COLUMN[current]] ?? base;
  if (vars) out = out.replace(/\{(\w+)\}/g, (match, name) => (vars[name] ?? match));
  return out;
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Til o'zgarganda komponent qayta chiziladi. */
export function useLang() {
  return useSyncExternalStore(subscribe, () => current);
}
