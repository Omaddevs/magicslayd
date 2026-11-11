// Ro'yxatdan o'tish, kirish, chiqish va parolni tiklash.
// Tasdiqlash kodi hisob bog'langan Telegram chatga bot orqali yuboriladi (SMS shart emas).
import { Router } from 'express';

import {
  CODE_RESEND_MS, CODE_TTL_MS, accountByPhone, accountByUser, checkCode, codeRow, createAccount, createSession,
  dropAllSessions, dropCode, dropSession, formatPhone, isVerifiedPhone, issueCode, maskPhone, normalizePhone,
  passwordProblem, phoneByResetToken, publicAccount, removeAccount, setPassword, verifyPassword,
} from '../accounts.js';
import { sessionOf, telegramUser } from '../auth.js';
import { nowStr, run } from '../db.js';
import { getSettings } from '../settings.js';
import { telegramReason, tg } from '../telegram.js';

const router = Router();

const fail = (res, status, error, extra = {}) => res.status(status).json({ error, ...extra });

// ===== Brute-force himoyasi (xotirada): kalit → urinish vaqtlari =====
const hits = new Map();
function limited(key, limit, windowMs) {
  const now = Date.now();
  const recent = (hits.get(key) ?? []).filter((time) => now - time < windowMs);
  hits.set(key, recent);
  return recent.length >= limit;
}
function hit(key) {
  const list = hits.get(key) ?? [];
  list.push(Date.now());
  hits.set(key, list);
}
setInterval(() => {
  const now = Date.now();
  for (const [key, times] of hits) if (times.every((time) => now - time > 60 * 60 * 1000)) hits.delete(key);
}, 10 * 60 * 1000).unref();

const MIN15 = 15 * 60 * 1000;
const HOUR = 60 * 60 * 1000;

/** Botdan xabar (xavfsizlik bildirishnomasi). Xato bo'lsa jim o'tadi — asosiy amal to'xtamasin. */
function notify(userId, text) {
  tg('sendMessage', { chat_id: userId, text, parse_mode: 'HTML' }).catch(() => {});
}

function signedIn(res, account) {
  res.json({ token: createSession(account.user_id), account: publicAccount(account) });
}

// Kirish oynasi uchun: bot nomi (brauzerda «Botda ro'yxatdan o'tish» havolasi)
router.get('/config', (req, res) => res.json({ bot: getSettings().bot_username || '' }));

// ===== Ro'yxatdan o'tish: telefon + parol. Faqat Telegram ichida (hisob Telegram user'iga bog'lanadi) =====
router.post('/register', async (req, res) => {
  const tgUser = telegramUser(req);
  if (!tgUser) {
    return fail(res, 403, "Ro'yxatdan o'tish Telegram ichida yoki bot orqali bo'ladi.", { code: 'TELEGRAM_REQUIRED' });
  }
  if (limited(`reg:${req.ip}`, 10, HOUR)) return fail(res, 429, "Juda ko'p urinish. Birozdan so'ng qayta urinib ko'ring.");

  const phone = normalizePhone(req.body?.phone);
  if (!phone) return fail(res, 400, "Telefon raqamni to'liq kiriting: +998 XX XXX XX XX", { field: 'phone' });
  const password = req.body?.password;
  const problem = passwordProblem(password);
  if (problem) return fail(res, 400, problem, { field: 'password' });

  const own = accountByUser(tgUser.id);
  if (own) {
    return fail(res, 409, `Siz ${formatPhone(own.phone)} raqami bilan ro'yxatdan o'tgansiz. «Kirish» orqali kiring.`, {
      field: 'phone', code: 'ALREADY_REGISTERED',
    });
  }
  const taken = accountByPhone(phone);
  if (taken) {
    // Raqam boshqa Telegram hisobida, lekin tasdiqlanmagan — haqiqiy egasi (kontakti tasdiqlangan) uni qaytarib oladi
    if (!taken.verified && isVerifiedPhone(tgUser.id, phone)) {
      removeAccount(taken.user_id);
      notify(taken.user_id, `⚠️ ${formatPhone(phone)} raqamining haqiqiy egasi uni tasdiqladi — hisob sizdan uzildi.`);
    } else {
      return fail(res, 409, "Bu raqam allaqachon ro'yxatdan o'tgan. «Kirish» ni tanlang.", { field: 'phone', code: 'PHONE_TAKEN' });
    }
  }
  hit(`reg:${req.ip}`);

  const fullName = [tgUser.first_name, tgUser.last_name].filter(Boolean).join(' ');
  run(
    'INSERT INTO users (id, full_name, username, joined_at) VALUES (?, ?, ?, ?) ' +
      'ON CONFLICT(id) DO UPDATE SET full_name = excluded.full_name, username = excluded.username',
    tgUser.id, fullName, tgUser.username ?? null, nowStr(),
  );
  const account = await createAccount(tgUser.id, phone, password, 'web');
  notify(
    tgUser.id,
    `✅ <b>Ro'yxatdan o'tdingiz!</b>\n\n📱 Login: <b>${formatPhone(phone)}</b>\n\n` +
      "Endi ilovaga istalgan qurilmadan shu raqam va parol bilan kirishingiz mumkin. Parolni hech kimga bermang.",
  );
  signedIn(res, account);
});

// ===== Kirish =====
router.post('/login', async (req, res) => {
  const phone = normalizePhone(req.body?.phone);
  if (!phone) return fail(res, 400, "Telefon raqamni to'liq kiriting.", { field: 'phone' });
  const password = String(req.body?.password ?? '');
  if (!password) return fail(res, 400, 'Parolni kiriting.', { field: 'password' });

  if (limited(`login-ip:${req.ip}`, 30, MIN15) || limited(`login:${phone}`, 8, MIN15)) {
    return fail(res, 429, "Juda ko'p noto'g'ri urinish. 15 daqiqadan so'ng qayta urinib ko'ring yoki parolni tiklang.");
  }
  const account = accountByPhone(phone);
  if (!account) {
    hit(`login-ip:${req.ip}`);
    return fail(res, 401, "Bu raqam ro'yxatdan o'tmagan.", { field: 'phone', code: 'NO_ACCOUNT' });
  }
  if (!(await verifyPassword(password, account.password_hash))) {
    hit(`login-ip:${req.ip}`);
    hit(`login:${phone}`);
    return fail(res, 401, "Parol noto'g'ri. Qayta urinib ko'ring yoki parolni tiklang.", { field: 'password' });
  }
  hits.delete(`login:${phone}`);
  const tgUser = telegramUser(req);
  if (tgUser?.id !== account.user_id) {
    notify(account.user_id, `🔐 Hisobingizga yangi qurilmadan kirildi (${nowStr()}).\nSiz bo'lmasangiz — darhol parolni o'zgartiring: /parol`);
  }
  signedIn(res, account);
});

// ===== Chiqish =====
router.post('/logout', (req, res) => {
  dropSession(req.get('X-Session'));
  res.json({ ok: true });
});

// ===== Parolni tiklash: 1) kod so'rash =====
router.post('/reset/request', async (req, res) => {
  const phone = normalizePhone(req.body?.phone);
  if (!phone) return fail(res, 400, "Telefon raqamni to'liq kiriting.", { field: 'phone' });
  const account = accountByPhone(phone);
  if (!account) return fail(res, 404, "Bu raqam ro'yxatdan o'tmagan.", { field: 'phone', code: 'NO_ACCOUNT' });

  const previous = codeRow(phone);
  const wait = previous ? previous.sent_at + CODE_RESEND_MS - Date.now() : 0;
  if (wait > 0) {
    return fail(res, 429, `Yangi kodni ${Math.ceil(wait / 1000)} soniyadan so'ng so'rash mumkin.`, { retryIn: Math.ceil(wait / 1000) });
  }
  if (limited(`code:${phone}`, 5, HOUR) || limited(`code-ip:${req.ip}`, 10, HOUR)) {
    return fail(res, 429, "Kod juda ko'p so'raldi. Bir soatdan so'ng qayta urinib ko'ring.");
  }

  const code = issueCode(phone);
  try {
    await tg('sendMessage', {
      chat_id: account.user_id,
      parse_mode: 'HTML',
      protect_content: true,
      text:
        `🔐 <b>Parolni tiklash kodi:</b> <code>${code}</code>\n\n` +
        `Kod ${CODE_TTL_MS / 60000} daqiqa amal qiladi. Uni hech kimga aytmang — xodimlarimiz ham so'ramaydi.\n` +
        "Siz so'ramagan bo'lsangiz, bu xabarga e'tibor bermang.",
    });
  } catch (error) {
    dropCode(phone);
    return fail(res, 502, telegramReason(error));
  }
  hit(`code:${phone}`);
  hit(`code-ip:${req.ip}`);
  res.json({
    ok: true,
    masked: maskPhone(phone),
    bot: getSettings().bot_username || '',
    retryIn: CODE_RESEND_MS / 1000,
    expiresIn: CODE_TTL_MS / 1000,
  });
});

// ===== 2) kodni tekshirish → qisqa muddatli token =====
router.post('/reset/verify', (req, res) => {
  const phone = normalizePhone(req.body?.phone);
  const code = String(req.body?.code ?? '').replace(/\D/g, '');
  if (!phone) return fail(res, 400, "Telefon raqam noto'g'ri.", { field: 'phone' });
  if (code.length !== 6) return fail(res, 400, '6 xonali kodni kiriting.', { field: 'code' });

  const result = checkCode(phone, code);
  if (result.ok) return res.json({ resetToken: result.resetToken });
  if (result.error === 'expired') return fail(res, 400, "Kod eskirgan. Yangi kod so'rang.", { field: 'code', code: 'EXPIRED' });
  if (result.error === 'attempts' || result.left <= 0) {
    return fail(res, 429, "Urinishlar tugadi. Yangi kod so'rang.", { field: 'code', code: 'EXPIRED' });
  }
  fail(res, 400, `Kod noto'g'ri. Yana ${result.left} ta urinish qoldi.`, { field: 'code' });
});

// ===== 3) yangi parol → avtomatik kirish =====
router.post('/reset/confirm', async (req, res) => {
  const phone = phoneByResetToken(String(req.body?.resetToken ?? ''));
  if (!phone) return fail(res, 400, 'Vaqt tugadi. Parolni tiklashni qaytadan boshlang.', { code: 'EXPIRED' });
  const password = req.body?.password;
  const problem = passwordProblem(password);
  if (problem) return fail(res, 400, problem, { field: 'password' });
  const account = accountByPhone(phone);
  if (!account) return fail(res, 404, 'Hisob topilmadi.');

  await setPassword(account.user_id, password);
  dropCode(phone);
  dropAllSessions(account.user_id); // boshqa qurilmalardagi eski sessiyalar yopiladi
  notify(account.user_id, "🔑 Parolingiz muvaffaqiyatli yangilandi. Boshqa qurilmalardagi sessiyalar yopildi.");
  signedIn(res, account);
});

// ===== Parolni o'zgartirish (kirgan user) =====
router.post('/password', async (req, res) => {
  const account = sessionOf(req);
  if (!account) return fail(res, 401, 'Hisobingizga kiring.', { code: 'AUTH_REQUIRED' });
  if (limited(`pwd:${account.user_id}`, 8, MIN15)) return fail(res, 429, "Juda ko'p urinish. Birozdan so'ng urinib ko'ring.");
  if (!(await verifyPassword(String(req.body?.current ?? ''), account.password_hash))) {
    hit(`pwd:${account.user_id}`);
    return fail(res, 400, "Joriy parol noto'g'ri.", { field: 'current' });
  }
  const password = req.body?.password;
  const problem = passwordProblem(password);
  if (problem) return fail(res, 400, problem, { field: 'password' });

  await setPassword(account.user_id, password);
  dropAllSessions(account.user_id);
  notify(account.user_id, "🔑 Parolingiz o'zgartirildi. Boshqa qurilmalardagi sessiyalar yopildi.");
  signedIn(res, account);
});

export default router;
