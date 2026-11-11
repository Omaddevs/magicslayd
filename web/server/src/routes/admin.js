// Web admin panel: umumiy statistika, foydalanuvchilar (qidirish, balans, xabar), to'lovlar (chekni ko'rish,
// tasdiqlash / rad etish), adminlar (faqat bot egasi). Kirish — admin hisobi (telefon + parol) — admins.js.
// To'lovni tasdiqlash botdagi tugma bilan bir xil yo'ldan o'tadi: web_orders (kind pay_review) → bot (handlers/web.py).
import express, { Router } from 'express';

import { formatPhone } from '../accounts.js';
import { OWNER_ID, PERMS, extraAdmins, hasPerm, isOwner, requirePerm } from '../admins.js';
import { ADMINS_EXTRA_MAX, AI_DAILY_BUDGET_USD, API_KEYS, BOT_TOKEN } from '../config.js';
import { all, nowStr, one, run } from '../db.js';
import { escapeHtml, tg } from '../telegram.js';
import { adminOnly } from './news.js';

const router = Router();
router.use('/admin', adminOnly);

const DAYS = 14;
const pad = (n) => String(n).padStart(2, '0');
const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** Oxirgi N kun bo'yicha qatorlar (bo'sh kunlar 0 bilan). sql: (dan) → [{ day, n }] */
function series(sql, ...args) {
  const start = new Date();
  start.setDate(start.getDate() - (DAYS - 1));
  const rows = Object.fromEntries(all(sql, `${dayKey(start)} 00:00`, ...args).map((r) => [r.day, r.n]));
  return Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return { day: dayKey(d), n: rows[dayKey(d)] ?? 0 };
  });
}

const count = (sql, ...args) => one(sql, ...args)?.n ?? 0;

// ===== Umumiy ko'rinish =====
router.get('/admin/overview', (req, res) => {
  // «Statistika» huquqi yo'q admin (masalan faqat cheklar) — daromad va userlar sonini ko'rmaydi, faqat kutayotgan cheklar
  if (!hasPerm(req.user.id, 'stats')) {
    return res.json({
      limited: true,
      money: { pending: hasPerm(req.user.id, 'payments') ? count("SELECT COUNT(*) AS n FROM payments WHERE status = 'pending'") : 0 },
    });
  }
  const today = `${dayKey(new Date())}%`;
  const week = new Date();
  week.setDate(week.getDate() - 7);
  const weekAgo = `${dayKey(week)} 00:00`;
  res.json({
    users: {
      total: count('SELECT COUNT(*) AS n FROM users'),
      today: count('SELECT COUNT(*) AS n FROM users WHERE joined_at LIKE ?', today),
      week: count('SELECT COUNT(*) AS n FROM users WHERE joined_at >= ?', weekAgo),
      accounts: count('SELECT COUNT(*) AS n FROM accounts'),
    },
    documents: {
      total: count('SELECT COUNT(*) AS n FROM documents'),
      today: count('SELECT COUNT(*) AS n FROM documents WHERE created_at LIKE ?', today),
      byKind: Object.fromEntries(all('SELECT kind, COUNT(*) AS n FROM documents GROUP BY kind').map((r) => [r.kind, r.n])),
    },
    money: {
      revenue: count("SELECT COALESCE(SUM(amount), 0) AS n FROM payments WHERE status = 'approved'"),
      today: count("SELECT COALESCE(SUM(amount), 0) AS n FROM payments WHERE status = 'approved' AND reviewed_at LIKE ?", today),
      week: count("SELECT COALESCE(SUM(amount), 0) AS n FROM payments WHERE status = 'approved' AND reviewed_at >= ?", weekAgo),
      balances: count('SELECT COALESCE(SUM(balance), 0) AS n FROM users'),
      pending: count("SELECT COUNT(*) AS n FROM payments WHERE status = 'pending'"),
      pendingSum: count("SELECT COALESCE(SUM(amount), 0) AS n FROM payments WHERE status = 'pending'"),
    },
    activeOrders: count("SELECT COUNT(*) AS n FROM web_orders WHERE status IN ('pending', 'working')"),
    series: {
      users: series('SELECT substr(joined_at, 1, 10) AS day, COUNT(*) AS n FROM users WHERE joined_at >= ? GROUP BY day'),
      documents: series('SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n FROM documents WHERE created_at >= ? GROUP BY day'),
      revenue: series(
        "SELECT substr(reviewed_at, 1, 10) AS day, SUM(amount) AS n FROM payments WHERE status = 'approved' AND reviewed_at >= ? GROUP BY day",
      ),
    },
  });
});

// ===== Foydalanuvchilar =====
const USER_FIELDS = `u.id, u.full_name, u.username, u.joined_at, u.balance, a.phone, a.verified,
  (SELECT COUNT(*) FROM documents d WHERE d.user_id = u.id) AS docs`;
const userOut = (u) => ({
  id: u.id, name: u.full_name || '', username: u.username || '', joinedAt: u.joined_at, balance: u.balance ?? 0,
  phone: u.phone ? formatPhone(u.phone) : '', verified: Boolean(u.verified), docs: u.docs ?? 0,
});

router.get('/admin/users', requirePerm('users'), (req, res) => {
  const q = String(req.query.q ?? '').trim().slice(0, 60);
  const digits = q.replace(/\D/g, '');
  let rows;
  if (!q) {
    rows = all(`SELECT ${USER_FIELDS} FROM users u LEFT JOIN accounts a ON a.user_id = u.id ORDER BY u.joined_at DESC LIMIT 50`);
  } else {
    const like = `%${q.replace(/^@/, '').replace(/[\\%_]/g, (c) => `\\${c}`)}%`;
    rows = all(
      `SELECT ${USER_FIELDS} FROM users u LEFT JOIN accounts a ON a.user_id = u.id
       WHERE CAST(u.id AS TEXT) = ? OR u.username LIKE ? ESCAPE '\\' OR u.full_name LIKE ? ESCAPE '\\'
          OR (? != '' AND a.phone LIKE ?)
       ORDER BY u.joined_at DESC LIMIT 50`,
      q, like, like, digits.length >= 4 ? digits : '', `%${digits}%`,
    );
  }
  res.json({ users: rows.map(userOut), total: count('SELECT COUNT(*) AS n FROM users') });
});

router.get('/admin/users/:id(\\d+)', requirePerm('users'), (req, res) => {
  const id = Number(req.params.id);
  const user = one(`SELECT ${USER_FIELDS} FROM users u LEFT JOIN accounts a ON a.user_id = u.id WHERE u.id = ?`, id);
  if (!user) return res.status(404).json({ error: 'User topilmadi.' });
  res.json({
    user: userOut(user),
    transactions: all('SELECT id, amount, kind, note, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 20', id),
    payments: all('SELECT id, amount, status, created_at FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT 10', id),
    documents: all('SELECT id, kind, title, created_at FROM documents WHERE user_id = ? ORDER BY id DESC LIMIT 10', id),
  });
});

const money = (n) => `${Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} so'm`;

/** Balansni o'zgartirish — botdagi /balans bilan bir xil: tranzaksiya yoziladi, userga xabar boradi. */
router.post('/admin/users/:id(\\d+)/balance', requirePerm('balance'), express.json({ limit: '2kb' }), async (req, res) => {
  const id = Number(req.params.id);
  const amount = Math.trunc(Number(req.body?.amount));
  if (!Number.isFinite(amount) || amount === 0 || Math.abs(amount) > 100_000_000) {
    return res.status(400).json({ error: "Summani to'g'ri kiriting." });
  }
  const changed = run('UPDATE users SET balance = balance + ? WHERE id = ? AND balance + ? >= 0', amount, id, amount).changes;
  if (!changed) return res.status(400).json({ error: "User topilmadi yoki balans manfiy bo'lib qoladi." });
  run("INSERT INTO transactions (user_id, amount, kind, note, created_at) VALUES (?, ?, 'admin', 'Admin tomonidan', ?)", id, amount, nowStr());
  const balance = one('SELECT balance FROM users WHERE id = ?', id).balance;
  const change = `${amount > 0 ? '+' : '−'}${money(Math.abs(amount))}`;
  tg('sendMessage', {
    chat_id: id, parse_mode: 'HTML',
    text: `💳 Balansingiz admin tomonidan o'zgartirildi: <b>${change}</b>\n👛 Balans: <b>${money(balance)}</b>`,
  }).catch(() => {});
  res.json({ balance });
});

router.post('/admin/users/:id(\\d+)/message', requirePerm('users'), express.json({ limit: '10kb' }), async (req, res) => {
  const text = String(req.body?.text ?? '').trim();
  if (!text) return res.status(400).json({ error: "Xabar bo'sh." });
  if (text.length > 3500) return res.status(400).json({ error: 'Xabar 3500 belgidan oshmasin.' });
  try {
    await tg('sendMessage', { chat_id: Number(req.params.id), parse_mode: 'HTML', text: `📩 <b>Admindan xabar</b>\n\n${escapeHtml(text)}` });
    res.json({ ok: true });
  } catch {
    res.status(502).json({ error: 'Yuborilmadi: user botni bloklagan yoki chat topilmadi.' });
  }
});

// ===== To'lovlar =====
const paymentOut = (p) => ({
  id: p.id, userId: p.user_id, name: p.full_name || '', username: p.username || '', amount: p.amount,
  status: p.status, fileType: p.file_type, createdAt: p.created_at, reviewedAt: p.reviewed_at, orderId: p.order_id,
  order: p.order_kind ? { kind: p.order_kind, params: JSON.parse(p.order_params || '{}'), status: p.order_status } : null,
});

router.get('/admin/payments', requirePerm('payments'), (req, res) => {
  const pendingOnly = req.query.status !== 'all';
  const rows = all(
    `SELECT p.*, u.full_name, u.username, o.kind AS order_kind, o.params AS order_params, o.status AS order_status
     FROM payments p LEFT JOIN users u ON u.id = p.user_id LEFT JOIN web_orders o ON o.id = p.order_id
     ${pendingOnly ? "WHERE p.status = 'pending'" : ''} ORDER BY p.id DESC LIMIT 50`,
  );
  res.json({ payments: rows.map(paymentOut) });
});

/** Chek rasmi / fayli — Telegram'dan olinib uzatiladi (bot tokeni brauzerga chiqmaydi). */
router.get('/admin/payments/:id(\\d+)/receipt', requirePerm('payments'), async (req, res) => {
  const payment = one('SELECT file_id, file_type FROM payments WHERE id = ?', Number(req.params.id));
  if (!payment?.file_id) return res.status(404).json({ error: 'Chek topilmadi.' });
  try {
    const file = await tg('getFile', { file_id: payment.file_id });
    const response = await fetch(`https://api.telegram.org/file/bot${BOT_TOKEN}/${file.file_path}`, { signal: AbortSignal.timeout(20_000) });
    if (!response.ok) throw new Error(String(response.status));
    const ext = (file.file_path.split('.').pop() || '').toLowerCase();
    res.setHeader('Content-Type', ext === 'pdf' ? 'application/pdf' : ext === 'png' ? 'image/png' : 'image/jpeg');
    res.setHeader('Cache-Control', 'private, max-age=3600');
    res.send(Buffer.from(await response.arrayBuffer()));
  } catch {
    res.status(502).json({ error: "Chekni Telegram'dan olib bo'lmadi." });
  }
});

router.post('/admin/payments/:id(\\d+)/review', requirePerm('payments'), express.json({ limit: '1kb' }), (req, res) => {
  const id = Number(req.params.id);
  const payment = one('SELECT status FROM payments WHERE id = ?', id);
  if (!payment) return res.status(404).json({ error: "To'lov topilmadi." });
  if (payment.status !== 'pending') return res.status(409).json({ error: "Bu to'lov allaqachon ko'rib chiqilgan." });
  const { lastInsertRowid } = run(
    "INSERT INTO web_orders (user_id, kind, params, price, status, created_at) VALUES (?, 'pay_review', ?, 0, 'pending', ?)",
    req.user.id, JSON.stringify({ payment_id: id, approve: req.body?.approve === true }), nowStr(),
  );
  res.status(202).json({ orderId: Number(lastInsertRowid) });
});

// ===== API va limitlar (bot yozadi: ai_usage, api_stats, meta → api_state:*, claude_credit) =====
const CF_FREE_IMAGES = 130; // Cloudflare bepul tarifi: kuniga ~10 000 neyron ≈ 130 FLUX rasm

function metaJson(key) {
  try {
    return JSON.parse(one('SELECT value FROM meta WHERE key = ?', key)?.value ?? 'null');
  } catch {
    return null;
  }
}

const tableExists = (name) => Boolean(one("SELECT 1 AS n FROM sqlite_master WHERE type = 'table' AND name = ?", name));

function apiCount(service, metric, day) {
  if (!tableExists('api_stats')) return 0;
  return one('SELECT value AS n FROM api_stats WHERE day = ? AND service = ? AND metric = ?', day, service, metric)?.n ?? 0;
}

router.get('/admin/apis', requirePerm('stats'), (req, res) => {
  const today = dayKey(new Date());
  const utcToday = new Date().toISOString().slice(0, 10);
  const weekStart = new Date();
  weekStart.setDate(weekStart.getDate() - 6);
  const hasUsage = tableExists('ai_usage');
  const sum = (where, ...args) => (hasUsage
    ? one(`SELECT COALESCE(SUM(cost), 0) AS cost, COUNT(*) AS n FROM ai_usage WHERE ${where}`, ...args)
    : { cost: 0, n: 0 });

  const todayUsage = sum('day = ?', today);
  const week = sum('day >= ?', dayKey(weekStart));
  const total = sum('1 = 1');
  const perDay = week.cost / 7;
  const credit = metaJson('claude_credit');
  let balance = null;
  if (credit && Number.isFinite(Number(credit.amount)) && credit.since) {
    const spent = sum('created_at >= ?', credit.since).cost;
    const left = Number(credit.amount) - spent;
    balance = { amount: Number(credit.amount), since: credit.since, spent, left, days: perDay > 0 && left > 0 ? left / perDay : null };
  }
  const daily = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (13 - i));
    return { day: dayKey(d), n: sum('day = ?', dayKey(d)).cost };
  });
  const models = hasUsage
    ? all('SELECT model, SUM(cost) AS cost, COUNT(*) AS n FROM ai_usage WHERE day >= ? GROUP BY model ORDER BY cost DESC', dayKey(weekStart))
    : [];

  const photo = (service) => ({
    enabled: service === 'wikimedia' ? true : API_KEYS[service],
    state: metaJson(`api_state:${service}`) ?? {},
    calls: apiCount(service, 'calls', today),
    errors: apiCount(service, 'errors', today),
  });

  res.json({
    claude: {
      enabled: API_KEYS.claude,
      state: metaJson('api_state:claude') ?? {},
      today: todayUsage, week, total, perDay,
      budget: AI_DAILY_BUDGET_USD,
      budgetLeft: AI_DAILY_BUDGET_USD ? Math.max(0, AI_DAILY_BUDGET_USD - todayUsage.cost) : null,
      rateLimited: apiCount('claude', 'rate_limited', today),
      balance, daily, models,
    },
    cloudflare: {
      enabled: API_KEYS.cloudflare,
      state: metaJson('api_state:cloudflare') ?? {},
      images: apiCount('cloudflare', 'images', utcToday),
      errors: apiCount('cloudflare', 'errors', utcToday),
      freeLimit: CF_FREE_IMAGES,
    },
    gemini: {
      enabled: API_KEYS.gemini,
      state: metaJson('api_state:gemini') ?? {},
      images: apiCount('gemini', 'images', utcToday),
      errors: apiCount('gemini', 'errors', utcToday),
    },
    pexels: photo('pexels'),
    pixabay: photo('pixabay'),
    wikimedia: photo('wikimedia'),
  });
});

/** Claude hisobidagi hozirgi balans (platform.claude.com → Billing) — shundan boshlab sarf ayirib boriladi. */
router.post('/admin/apis/credit', requirePerm('stats'), express.json({ limit: '1kb' }), (req, res) => {
  const amount = Number(String(req.body?.amount ?? '').replace(',', '.'));
  if (!Number.isFinite(amount) || amount < 0 || amount > 100_000) {
    return res.status(400).json({ error: "Summani dollarda to'g'ri kiriting." });
  }
  run(
    "INSERT INTO meta (key, value) VALUES ('claude_credit', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
    JSON.stringify({ amount: Math.round(amount * 100) / 100, since: nowStr() }),
  );
  res.json({ ok: true });
});

/** pay_review / admins natijasi (bot bajargach). */
router.get('/admin/review/:id(\\d+)', (req, res) => {
  const order = one(
    "SELECT status, error FROM web_orders WHERE id = ? AND kind IN ('pay_review', 'admins') AND user_id = ?",
    Number(req.params.id), req.user.id,
  );
  if (!order) return res.status(404).json({ error: 'Topilmadi.' });
  res.json(order);
});

// ===== Adminlar — faqat bot egasi (.env → ADMIN_ID). Qo'shish / o'chirishni bot bajaradi (bot/handlers/admins.py):
// yangi adminga Telegram xabari va admin menyusi boradi =====
function ownerOnly(req, res, next) {
  if (isOwner(req.user?.id)) return next();
  return res.status(403).json({ error: 'Adminlarni faqat bot egasi boshqaradi.' });
}

router.get('/admin/admins', ownerOnly, (req, res) => {
  const owner = one('SELECT full_name AS name, username FROM users WHERE id = ?', OWNER_ID) ?? {};
  res.json({
    owner: { userId: OWNER_ID, name: owner.name || '', username: owner.username || '' },
    admins: extraAdmins(),
    max: ADMINS_EXTRA_MAX,
  });
});

function queueAdminChange(req, res, action, userId, extra = {}) {
  if (!Number.isInteger(userId) || userId <= 0 || userId > 1e15) {
    return res.status(400).json({ error: "Telegram ID noto'g'ri — faqat raqamlar (masalan 123456789)." });
  }
  const { lastInsertRowid } = run(
    "INSERT INTO web_orders (user_id, kind, params, price, status, created_at) VALUES (?, 'admins', ?, 0, 'pending', ?)",
    req.user.id, JSON.stringify({ action, user_id: userId, ...extra }), nowStr(),
  );
  return res.status(202).json({ orderId: Number(lastInsertRowid) });
}

router.post('/admin/admins', ownerOnly, express.json({ limit: '1kb' }), (req, res) =>
  queueAdminChange(req, res, 'add', Number(String(req.body?.userId ?? '').trim())));

router.delete('/admin/admins/:id(\\d+)', ownerOnly, (req, res) =>
  queueAdminChange(req, res, 'remove', Number(req.params.id)));

// Huquqlar: { perms: ['payments', 'users', ...] } — bot saqlaydi, adminning menyusini yangilaydi va unga xabar yuboradi
router.put('/admin/admins/:id(\\d+)/perms', ownerOnly, express.json({ limit: '1kb' }), (req, res) => {
  const perms = Array.isArray(req.body?.perms) ? req.body.perms.filter((p) => PERMS.includes(p)) : null;
  if (!perms) return res.status(400).json({ error: "Huquqlar ro'yxati noto'g'ri." });
  return queueAdminChange(req, res, 'perms', Number(req.params.id), { perms });
});

export default router;
