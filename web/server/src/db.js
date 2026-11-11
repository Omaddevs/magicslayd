import { existsSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';

import { DB_PATH } from './config.js';

if (!existsSync(DB_PATH)) {
  console.error(`Baza topilmadi: ${DB_PATH}\nAvval botni bir marta ishga tushiring (u bazani yaratadi) yoki DB_PATH ni yozing.`);
  process.exit(1);
}

// Bot (Python) bilan bitta baza — WAL rejimida o'qish va yozish bir-birini to'smaydi
export const db = new DatabaseSync(DB_PATH);
db.exec('PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;');

// Bot jadvallari (bot.py yaratadi). Bot yangilanmagan bo'lsa ham ilova ishlashi uchun takrorlanadi
db.exec(`
  CREATE TABLE IF NOT EXISTS web_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, params TEXT,
    price INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
    charged INTEGER NOT NULL DEFAULT 0, error TEXT, document_id INTEGER, created_at TEXT, finished_at TEXT);
  CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, title TEXT, pages INTEGER, file_id TEXT, file_type TEXT,
    downloads INTEGER NOT NULL DEFAULT 0, created_at TEXT);
  CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
  CREATE TABLE IF NOT EXISTS ai_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT, source TEXT, kind TEXT,
    status TEXT NOT NULL DEFAULT 'queued', error TEXT, created_at TEXT, finished_at TEXT);
  CREATE INDEX IF NOT EXISTS ai_requests_user ON ai_requests (user_key, created_at);
  CREATE TABLE IF NOT EXISTS diplomas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT, data TEXT NOT NULL,
    paid INTEGER NOT NULL DEFAULT 0, document_id INTEGER, created_at TEXT, updated_at TEXT);
  CREATE INDEX IF NOT EXISTS diplomas_user ON diplomas (user_id, id);
  CREATE TABLE IF NOT EXISTS dissertations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT, data TEXT NOT NULL,
    paid INTEGER NOT NULL DEFAULT 0, document_id INTEGER, created_at TEXT, updated_at TEXT);
  CREATE INDEX IF NOT EXISTS dissertations_user ON dissertations (user_id, id);

  -- Telefon + parol hisoblari (bot ham yozadi: /royxat). user_id — Telegram ID (users.id)
  CREATE TABLE IF NOT EXISTS accounts (
    user_id INTEGER PRIMARY KEY, phone TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0, source TEXT, created_at TEXT, updated_at TEXT);
  CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT, expires_at INTEGER NOT NULL);
  CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions (user_id);
  CREATE TABLE IF NOT EXISTS auth_codes (
    phone TEXT PRIMARY KEY, code_hash TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    expires_at INTEGER NOT NULL, sent_at INTEGER NOT NULL, reset_token_hash TEXT, reset_expires_at INTEGER);
  -- Telegram kontakti orqali tasdiqlangan raqamlar (bot yozadi)
  CREATE TABLE IF NOT EXISTS verified_phones (user_id INTEGER PRIMARY KEY, phone TEXT NOT NULL, created_at TEXT);

  -- Faqat ilovaga tegishli jadvallar
  CREATE TABLE IF NOT EXISTS web_bookmarks (
    user_id INTEGER, material_id INTEGER, created_at TEXT, PRIMARY KEY (user_id, material_id));
`);

const hasUsers = db.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").get();
if (!hasUsers) {
  console.error("Bazada «users» jadvali yo'q — bu botning bazasi emas. DB_PATH ni tekshiring.");
  process.exit(1);
}

// Bot bilan bir xil vaqt formati: «2026-11-02 14:05»
const pad = (n) => String(n).padStart(2, '0');
export function nowStr() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const todayStr = () => nowStr().slice(0, 10);

export const one = (sql, ...args) => db.prepare(sql).get(...args);
export const all = (sql, ...args) => db.prepare(sql).all(...args);
export const run = (sql, ...args) => db.prepare(sql).run(...args);
