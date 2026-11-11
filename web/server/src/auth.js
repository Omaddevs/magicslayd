import crypto from 'node:crypto';

import { sessionAccount } from './accounts.js';
import { BOT_TOKEN, DEV_USER_ID } from './config.js';
import { one } from './db.js';

const MAX_AGE = 24 * 60 * 60; // initData shuncha soniyadan eski bo'lsa qabul qilinmaydi
const SECRET = crypto.createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest();

/** Telegram Mini App initData imzosini tekshiradi. To'g'ri bo'lsa — user obyekti, aks holda null.
 *  https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app */
export function verifyInitData(initData) {
  const params = new URLSearchParams(initData);
  const hash = params.get('hash');
  if (!hash) return null;
  params.delete('hash');
  const check = [...params.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
  const expected = crypto.createHmac('sha256', SECRET).update(check).digest('hex');
  if (expected.length !== hash.length || !crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(hash))) {
    return null;
  }
  if (Date.now() / 1000 - Number(params.get('auth_date')) > MAX_AGE) return null;
  try {
    return JSON.parse(params.get('user'));
  } catch {
    return null;
  }
}

/** So'rov shu kompyuterning o'zidanmi. Tunnel (cloudflared, ngrok) ham localhost'dan ulanadi,
 *  lekin asl manzilni sarlavhada yuboradi — bunday so'rovlarga DEV kirish berilmaydi. */
function fromThisComputer(req) {
  const address = req.socket.remoteAddress ?? '';
  const loopback = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(address);
  const forwarded = ['x-forwarded-for', 'cf-connecting-ip', 'x-real-ip', 'forwarded'].some((h) => req.get(h));
  return loopback && !forwarded;
}

/** Telegram user'i: «Authorization: tma <initData>» (yoki lokal DEV rejim). Bo'lmasa — null. */
export function telegramUser(req) {
  const header = req.get('Authorization') || '';
  const user = header.startsWith('tma ') ? verifyInitData(header.slice(4)) : null;
  if (user?.id) return user;
  if (DEV_USER_ID && fromThisComputer(req)) {
    // Bazadagi ism va username saqlanib qolsin (bootstrap ularni qayta yozadi)
    const row = one('SELECT full_name, username FROM users WHERE id = ?', DEV_USER_ID);
    return { id: DEV_USER_ID, first_name: row?.full_name || 'Dev', username: row?.username ?? undefined };
  }
  return null;
}

/** Telefon + parol bilan kirilgan sessiya: «X-Session: <token>». */
export const sessionOf = (req) => sessionAccount(req.get('X-Session'));

/** Har bir /api so'rovida.
 *  - Sessiya bor → hisob egasi nomidan (Telegram ichida ham, oddiy brauzerda ham)
 *  - Faqat Telegram → mehmon: ko'rish mumkin, yaratish / like / saqlash — ro'yxatdan o'tgach
 *  - Hech biri yo'q → 401 (ilova kirish oynasini ko'rsatadi) */
export function auth(req, res, next) {
  const tgUser = telegramUser(req);
  const account = sessionOf(req);
  req.tgUser = tgUser;
  req.account = account;
  if (account) {
    if (tgUser?.id === account.user_id) {
      req.user = tgUser;
    } else {
      const row = one('SELECT full_name, username FROM users WHERE id = ?', account.user_id);
      req.user = { id: account.user_id, first_name: row?.full_name || 'Foydalanuvchi', username: row?.username ?? undefined, fromSession: true };
    }
  } else if (tgUser) {
    req.user = tgUser;
  } else {
    return res.status(401).json({ error: 'Hisobingizga kiring.', code: 'LOGIN_REQUIRED' });
  }
  next();
}

// Mehmon (ro'yxatdan o'tmagan) ham ochadigan so'rovlar — faqat ko'rish
const GUEST_ROUTES = [
  ['GET', /^\/bootstrap$/],
  ['GET', /^\/materials$/],
  ['GET', /^\/news$/],
  ['GET', /^\/search$/],
  ['POST', /^\/materials\/\d+\/send$/],
  // Bildirishnomalar — hamma userlarga (mehmonga ham) yuboriladi, o'qish ham ochiq
  ['GET', /^\/notifications(\/unread-count|\/\d+)?$/],
  ['POST', /^\/notifications\/(\d+\/read|read-all)$/],
];

/** Qolgan hamma narsa (yaratish, like, saqlash, hamyon, loyihalar) — hisob talab qiladi. */
export function requireAccount(req, res, next) {
  if (req.account || GUEST_ROUTES.some(([method, path]) => method === req.method && path.test(req.path))) return next();
  res.status(401).json({ error: "Avval ro'yxatdan o'ting yoki hisobingizga kiring.", code: 'AUTH_REQUIRED' });
}
