import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseEnv } from 'node:util';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

// ===== O'zining .env fayli =====
const ownEnv = path.join(ROOT, '.env');
if (existsSync(ownEnv)) process.loadEnvFile(ownEnv);

// ===== Botning .env fayli — token va admin bot bilan bir xil bo'lishi shart =====
export const BOT_DIR = path.resolve(ROOT, process.env.BOT_DIR || '../../bot');
const botEnvFile = path.join(BOT_DIR, '.env');
const botEnv = existsSync(botEnvFile) ? parseEnv(readFileSync(botEnvFile, 'utf8')) : {};
const env = (key, fallback = '') => (process.env[key] ?? botEnv[key] ?? fallback).trim();

export const BOT_TOKEN = env('BOT_TOKEN');
// Admin panel (API va limitlar) uchun: faqat kalit BORMI — qiymatlari hech qachon brauzerga chiqmaydi
const budget = Number(env('AI_DAILY_BUDGET_USD', '3'));
export const AI_DAILY_BUDGET_USD = Number.isFinite(budget) && budget > 0 ? budget : 0;
export const API_KEYS = {
  claude: Boolean(env('ANTHROPIC_API_KEY')),
  pexels: Boolean(env('PEXELS_API_KEY')),
  pixabay: Boolean(env('PIXABAY_API_KEY')),
  gemini: Boolean(env('GEMINI_API_KEY')),
  cloudflare: Boolean(env('CLOUDFLARE_ACCOUNT_ID') && env('CLOUDFLARE_API_TOKEN')),
};
export const ADMIN_ID = /^\d+$/.test(env('ADMIN_ID')) ? Number(env('ADMIN_ID')) : null; // bot egasi
// Egadan tashqari qo'shimcha adminlar soni (bot: config.ADMINS_EXTRA_MAX)
export const ADMINS_EXTRA_MAX = /^\d+$/.test(env('ADMINS_EXTRA_MAX')) ? Number(env('ADMINS_EXTRA_MAX')) : 2;

const dataDir = env('DATA_DIR') ? path.resolve(BOT_DIR, env('DATA_DIR')) : BOT_DIR;
export const DB_PATH = process.env.DB_PATH ? path.resolve(ROOT, process.env.DB_PATH) : path.join(dataDir, 'bot.db');

// Taqdimot loyihalari (muharrir uchun) — bot bazasi yonida: <DATA_DIR>/decks/<hujjat_id>/
export const DECKS_DIR = path.join(path.dirname(DB_PATH), 'decks');
// Referat / mustaqil ish / kurs ishi loyihalari (prezentatsiya_bot/documents/storage.py): <DATA_DIR>/papers/<hujjat_id>/
export const PAPERS_DIR = path.join(path.dirname(DB_PATH), 'papers');
// Diplom ishi fayllari (prezentatsiya_bot/diploma/storage.py): <DATA_DIR>/diplomas/<id>/
export const DIPLOMAS_DIR = path.join(path.dirname(DB_PATH), 'diplomas');
// Dissertatsiya fayllari (prezentatsiya_bot/dissertation/storage.py): <DATA_DIR>/dissertations/<id>/
export const DISS_DIR = path.join(path.dirname(DB_PATH), 'dissertations');
// Maqolalar (prezentatsiya_bot/articles/storage.py): <DATA_DIR>/articles/<hujjat_id>/
export const ARTICLES_DIR = path.join(path.dirname(DB_PATH), 'articles');

export const PORT = Number(process.env.PORT) || 3001;
export const IS_PROD = process.env.NODE_ENV === 'production';
// Lokal sinov: Telegram'siz brauzerda ochilganda shu user sifatida kiriladi
export const DEV_USER_ID = !IS_PROD && /^\d+$/.test(process.env.DEV_USER_ID || '') ? Number(process.env.DEV_USER_ID) : null;

// Build qilingan React ilova — server uni o'zi tarqatadi
export const CLIENT_DIST = path.resolve(ROOT, '../client/dist');

if (!BOT_TOKEN) {
  console.error(`BOT_TOKEN topilmadi! ${botEnvFile} faylini tekshiring yoki BOT_DIR ni to'g'ri yozing.`);
  process.exit(1);
}
