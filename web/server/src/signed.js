import crypto from 'node:crypto';

import { BOT_TOKEN } from './config.js';

// Qisqa muddatli imzolangan havolalar: <img>, <video>, Telegram.downloadFile Authorization sarlavhasini
// yubora olmaydi — shuning uchun ruxsat havolaning o'ziga yoziladi
const SECRET = crypto.createHmac('sha256', 'SlaydLinks').update(BOT_TOKEN).digest();
const sign = (payload) => crypto.createHmac('sha256', SECRET).update(payload).digest('base64url');

/** parts — nuqtasiz qiymatlar (masalan ['documents', 12, 777]); ttl — soniya. */
export function makeToken(parts, ttl) {
  const payload = [...parts, Math.floor(Date.now() / 1000) + ttl].join('.');
  return `${Buffer.from(payload).toString('base64url')}.${sign(payload)}`;
}

/** Imzo to'g'ri va muddati o'tmagan bo'lsa — qismlar ro'yxati (muddatsiz), aks holda null. */
export function readToken(token) {
  const [encoded, signature] = String(token).split('.');
  if (!encoded || !signature) return null;
  const payload = Buffer.from(encoded, 'base64url').toString();
  const expected = sign(payload);
  if (expected.length !== signature.length || !crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature))) {
    return null;
  }
  const parts = payload.split('.');
  if (Date.now() / 1000 > Number(parts.pop())) return null;
  return parts;
}
