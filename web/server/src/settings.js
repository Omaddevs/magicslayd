import { hasPerm } from './admins.js';
import { one } from './db.js';

// Bot ishga tushganda meta jadvaliga haqiqiy sozlamalarni yozadi (handlers/web.py).
// Bu qiymatlar faqat bot hali yangilanmagan bo'lsa ishlatiladi — bot config.py bilan bir xil
const DEFAULTS = {
  bot_username: '',
  support: '',
  pdf: false,
  slides: { options: [5, 8, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 70, 80], price: 500, fixed: 4, plan_min: 1, plan_max: 10 },
  diploma: { page_price: 700, min: 40, max: 150, options: [50, 60, 70, 80, 90, 100] },
  dissertation: {
    page_price: 800, min: 50, max: 300,
    types: {
      master: { name: 'Magistrlik dissertatsiyasi', pages: 80, options: [70, 80, 90, 100], chapters: 3 },
      phd: { name: 'PhD dissertatsiyasi', pages: 140, options: [120, 130, 140, 150, 160], chapters: 3 },
      dsc: { name: 'DSc dissertatsiyasi', pages: 220, options: [200, 220, 250], chapters: 4 },
      other: { name: 'Boshqa ilmiy tadqiqot', pages: 80, options: [60, 80, 100, 120], chapters: 3 },
    },
  },
  pages: { referat: [5, 10, 15, 20, 25, 30], mustaqil: [5, 10, 15, 20, 25, 30], kurs: [20, 25, 30, 35, 40, 45, 50] },
  page_range: { referat: [3, 50], mustaqil: [3, 50], kurs: [15, 80] }, // o'zi yozadigan betlar (bot: config.PAGE_RANGE)
  page_price: { referat: 500, mustaqil: 500, kurs: 600 },
  // Maqola (bot: articles/model.py, config.article_price) — bot ishga tushganda haqiqiysini yozadi
  article: {
    sizes: { short: [500, 700], medium: [1000, 1500], long: [2000, 3000] },
    words_min: 300, words_max: 5000, price_per_100: 200, price_min: 1500,
  },
  languages: { uz: "🇺🇿 O'zbekcha", ru: '🇷🇺 Русский', en: '🇬🇧 English' },
  // AI yordamchi — bot config / assistant/service.py bilan bir xil (bot ishga tushganda haqiqiysini yozadi)
  ai: {
    types: {
      pres: { label: 'Taqdimot', unit: 'slayd', min: 5, max: 20, default: 10 },
      referat: { label: 'Referat', unit: 'bet', min: 5, max: 20, default: 10 },
      mustaqil: { label: 'Mustaqil ish', unit: 'bet', min: 5, max: 15, default: 8 },
      kurs: { label: 'Kurs ishi', unit: 'bet', min: 15, max: 40, default: 25 },
    },
    languages: { uz: "O'zbek (lotin)", uz_cyrl: 'Ўзбек (кирилл)', ru: 'Русский' },
    topic_min: 5, topic_max: 200, subject_max: 100, daily_limit: 3, per_minute: 2,
  },
  // Haqiqiy kartalar faqat bot yuborgan sozlamada (bot .env → PAYMENT_CARDS)
  payment: { enabled: false, cards: [], min: 5000, max: 5000000, options: [10000, 20000, 50000, 100000], pending_max: 3 },
  themes: {
    cosmos: { name: '🌌 Kosmos', dark: true, bg: '0B1026', bg2: '2A1B5C', accent: '22D3EE', accent2: 'A855F7', card: '1A2148', text: 'F5F7FF', muted: 'A5B0D6' },
    sunset: { name: '🔥 Shafaq', dark: true, bg: '1C1917', bg2: '4A1D1F', accent: 'FB923C', accent2: 'F43F5E', card: '2C2422', text: 'FFF7ED', muted: 'D6B8A8' },
    ocean: { name: '🌊 Okean', dark: true, bg: '042F2E', bg2: '0C4A6E', accent: '2DD4BF', accent2: '38BDF8', card: '0B3B45', text: 'F0FDFA', muted: '9CC9C9' },
    nature: { name: '🌿 Tabiat', dark: false, bg: 'F7F5EE', bg2: 'E3EEDC', accent: '2F855A', accent2: 'D69E2E', card: 'FFFFFF', text: '1F2A1F', muted: '5F6B5F' },
    business: { name: '💼 Biznes', dark: false, bg: 'FFFFFF', bg2: 'E8EEFB', accent: '1D4ED8', accent2: '0EA5E9', card: 'F3F6FD', text: '0F172A', muted: '55627A' },
    pastel: { name: '🍬 Pastel', dark: false, bg: 'FFF5F7', bg2: 'EDE9FE', accent: 'DB2777', accent2: '7C3AED', card: 'FFFFFF', text: '3B1F35', muted: '7A6275' },
  },
};

export function getSettings() {
  const row = one("SELECT value FROM meta WHERE key = 'web_config'");
  if (!row) return DEFAULTS;
  try {
    return { ...DEFAULTS, ...JSON.parse(row.value) };
  } catch {
    return DEFAULTS;
  }
}

export const DOC_KINDS = ['referat', 'mustaqil', 'kurs'];
export const ORDER_KINDS = ['pres', ...DOC_KINDS, 'maqola'];
export const ARTICLE_TYPES = ['general', 'scientific', 'analytical', 'journalistic', 'review'];

/** Maqola narxi: har 100 so'z uchun, kamida price_min (bot: config.article_price). */
export function articlePrice(words, settings = getSettings()) {
  const { price_per_100: per100, price_min: min } = settings.article;
  return Math.max(min, Math.ceil(words / 100) * per100);
}

/** Buyurtma narxi (admin uchun bepul — bot bilan bir xil qoida). */
export function orderPrice(userId, kind, params, settings = getSettings()) {
  if (hasPerm(userId, 'free')) return 0; // admin «bepul buyurtma» huquqi bilan
  if (kind === 'pres') return params.slides * settings.slides.price;
  if (kind === 'maqola') return articlePrice(params.words, settings);
  return params.pages * settings.page_price[kind];
}

export const money = (amount) => `${amount.toLocaleString('en-US').replace(/,/g, ' ')} so'm`;
