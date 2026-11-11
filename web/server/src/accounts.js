// Telefon + parol hisoblari. Hisob Telegram user'iga (users.id) bog'lanadi — balans, hujjatlar va
// fayllar Telegram chatga yuborilishi o'zgarmaydi. Bot (prezentatsiya_bot/accounts.py) ham shu jadvallar bilan ishlaydi.
import crypto from 'node:crypto';
import { promisify } from 'node:util';

import { nowStr, one, run } from './db.js';

const scrypt = promisify(crypto.scrypt);

// Bot (Python hashlib.scrypt) bilan bir xil parametrlar — ikkalasi ham bir-birining xeshini tekshira oladi
const N = 16384;
const R = 8;
const P = 1;
const KEY_LEN = 64;

export const SESSION_MS = 90 * 24 * 60 * 60 * 1000; // 90 kun
export const PASSWORD_MIN = 6;
export const PASSWORD_MAX = 64;

const sha256 = (text) => crypto.createHash('sha256').update(text).digest('hex');

export async function hashPassword(password) {
  const salt = crypto.randomBytes(16);
  const key = await scrypt(password.normalize('NFKC'), salt, KEY_LEN, { N, r: R, p: P });
  return `scrypt$${N}$${R}$${P}$${salt.toString('base64')}$${key.toString('base64')}`;
}

export async function verifyPassword(password, stored) {
  const [alg, n, r, p, salt, hash] = String(stored ?? '').split('$');
  if (alg !== 'scrypt' || !salt || !hash) return false;
  const expected = Buffer.from(hash, 'base64');
  const key = await scrypt(password.normalize('NFKC'), Buffer.from(salt, 'base64'), expected.length, {
    N: Number(n), r: Number(r), p: Number(p), maxmem: 64 * 1024 * 1024,
  });
  return key.length === expected.length && crypto.timingSafeEqual(key, expected);
}

/** Parol talablari. Xato bo'lsa — matn, to'g'ri bo'lsa — null. */
export function passwordProblem(password) {
  if (typeof password !== 'string' || password.length < PASSWORD_MIN) return `Parol kamida ${PASSWORD_MIN} belgidan iborat bo'lsin.`;
  if (password.length > PASSWORD_MAX) return `Parol ${PASSWORD_MAX} belgidan oshmasin.`;
  if (!/\p{L}/u.test(password) || !/\d/.test(password)) return "Parolda kamida bitta harf va bitta raqam bo'lsin.";
  return null;
}

/** «+998 90 123-45-67», «901234567» → «998901234567». Faqat O'zbekiston raqamlari. */
export function normalizePhone(raw) {
  let digits = String(raw ?? '').replace(/\D/g, '');
  if (digits.length === 9) digits = `998${digits}`;
  return /^998\d{9}$/.test(digits) ? digits : null;
}

export const formatPhone = (d) => `+998 ${d.slice(3, 5)} ${d.slice(5, 8)} ${d.slice(8, 10)} ${d.slice(10, 12)}`;
export const maskPhone = (d) => `+998 ${d.slice(3, 5)} *** ** ${d.slice(10, 12)}`;

// ===== Hisoblar =====
export const accountByUser = (userId) => one('SELECT * FROM accounts WHERE user_id = ?', userId);
export const accountByPhone = (phone) => one('SELECT * FROM accounts WHERE phone = ?', phone);

/** Ilovaga yuboriladigan ko'rinish (xesh va ichki maydonlarsiz). */
export function publicAccount(row) {
  if (!row) return null;
  return { phone: formatPhone(row.phone), digits: row.phone.slice(3), verified: Boolean(row.verified), createdAt: row.created_at };
}

/** Telegram kontakti orqali tasdiqlangan raqam (bot «verified_phones» ga yozadi). */
export function isVerifiedPhone(userId, phone) {
  return Boolean(one('SELECT 1 FROM verified_phones WHERE user_id = ? AND phone = ?', userId, phone));
}

export async function createAccount(userId, phone, password, source) {
  const verified = isVerifiedPhone(userId, phone) ? 1 : 0;
  const now = nowStr();
  run(
    'INSERT INTO accounts (user_id, phone, password_hash, verified, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
    userId, phone, await hashPassword(password), verified, source, now, now,
  );
  return accountByUser(userId);
}

export async function setPassword(userId, password) {
  run('UPDATE accounts SET password_hash = ?, updated_at = ? WHERE user_id = ?', await hashPassword(password), nowStr(), userId);
}

/** Tasdiqlanmagan (begona kiritgan bo'lishi mumkin) hisobni o'chiradi — raqamning haqiqiy egasi kelganda. */
export function removeAccount(userId) {
  run('DELETE FROM auth_sessions WHERE user_id = ?', userId);
  run('DELETE FROM accounts WHERE user_id = ?', userId);
}

// ===== Sessiyalar: bazada faqat tokenning xeshi saqlanadi =====
export function createSession(userId) {
  const token = crypto.randomBytes(32).toString('base64url');
  run(
    'INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
    sha256(token), userId, nowStr(), Date.now() + SESSION_MS,
  );
  return token;
}

export function sessionAccount(token) {
  if (!token || token.length > 128) return null;
  return one(
    'SELECT a.* FROM auth_sessions s JOIN accounts a ON a.user_id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?',
    sha256(token), Date.now(),
  ) ?? null;
}

export function dropSession(token) {
  if (token) run('DELETE FROM auth_sessions WHERE token_hash = ?', sha256(token));
}

export function dropAllSessions(userId) {
  run('DELETE FROM auth_sessions WHERE user_id = ?', userId);
}

// ===== Parolni tiklash kodlari =====
export const CODE_TTL_MS = 5 * 60 * 1000;
export const CODE_RESEND_MS = 60 * 1000;
export const CODE_ATTEMPTS = 5;
export const RESET_TTL_MS = 10 * 60 * 1000;

const codeHash = (phone, code) => sha256(`${phone}:${code}`);

export const codeRow = (phone) => one('SELECT * FROM auth_codes WHERE phone = ?', phone);

export function issueCode(phone) {
  const code = String(crypto.randomInt(100000, 1000000));
  const now = Date.now();
  run(
    'INSERT INTO auth_codes (phone, code_hash, attempts, expires_at, sent_at, reset_token_hash, reset_expires_at) ' +
      'VALUES (?, ?, 0, ?, ?, NULL, NULL) ON CONFLICT(phone) DO UPDATE SET code_hash = excluded.code_hash, ' +
      'attempts = 0, expires_at = excluded.expires_at, sent_at = excluded.sent_at, reset_token_hash = NULL, reset_expires_at = NULL',
    phone, codeHash(phone, code), now + CODE_TTL_MS, now,
  );
  return code;
}

export const dropCode = (phone) => run('DELETE FROM auth_codes WHERE phone = ?', phone);

/** Kodni tekshiradi: { ok, resetToken } yoki { error, left }. */
export function checkCode(phone, code) {
  const row = codeRow(phone);
  if (!row || !row.code_hash || row.expires_at < Date.now()) return { error: 'expired' };
  if (row.attempts >= CODE_ATTEMPTS) return { error: 'attempts' };
  const given = Buffer.from(codeHash(phone, String(code)));
  const expected = Buffer.from(row.code_hash);
  if (given.length !== expected.length || !crypto.timingSafeEqual(given, expected)) {
    run('UPDATE auth_codes SET attempts = attempts + 1 WHERE phone = ?', phone);
    return { error: 'wrong', left: CODE_ATTEMPTS - row.attempts - 1 };
  }
  // Kod bir martalik: o'rniga qisqa muddatli «yangi parol qo'yish» tokeni beriladi
  const resetToken = crypto.randomBytes(24).toString('base64url');
  run(
    "UPDATE auth_codes SET code_hash = '', reset_token_hash = ?, reset_expires_at = ? WHERE phone = ?",
    sha256(resetToken), Date.now() + RESET_TTL_MS, phone,
  );
  return { ok: true, resetToken };
}

export function phoneByResetToken(resetToken) {
  if (!resetToken || resetToken.length > 128) return null;
  return one('SELECT phone FROM auth_codes WHERE reset_token_hash = ? AND reset_expires_at > ?', sha256(resetToken), Date.now())?.phone ?? null;
}

// Muddati o'tgan sessiya va kodlar vaqti-vaqti bilan tozalanadi
setInterval(() => {
  const now = Date.now();
  run('DELETE FROM auth_sessions WHERE expires_at < ?', now);
  run('DELETE FROM auth_codes WHERE expires_at < ? AND (reset_expires_at IS NULL OR reset_expires_at < ?)', now, now);
}, 60 * 60 * 1000).unref();
