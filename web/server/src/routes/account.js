import { Router } from 'express';

import { accountByUser, publicAccount } from '../accounts.js';
import { hasPerm, isAdmin, isOwner, permsOf } from '../admins.js';
import { all, nowStr, one, run } from '../db.js';
import { getSettings, money } from '../settings.js';
import { telegramReason, tg } from '../telegram.js';
import { unreadCount } from './notifications.js';
import { waitingOrder } from './orders.js';

const router = Router();

const TITLE_FIELDS = ['university', 'faculty', 'subject', 'student', 'group', 'teacher', 'city'];
const TITLE_MAX = 150;

const balanceOf = (userId) => one('SELECT balance FROM users WHERE id = ?', userId)?.balance ?? 0;

// ===== Ilova ochilganda: user, balans, sozlamalar =====
router.get('/bootstrap', (req, res) => {
  const user = req.user;
  const tgUser = req.tgUser;
  // Bot bilan bir xil: yangi Telegram user qo'shiladi, borining ismi yangilanadi (balans saqlanadi)
  if (tgUser) {
    run(
      'INSERT INTO users (id, full_name, username, joined_at) VALUES (?, ?, ?, ?) ' +
        'ON CONFLICT(id) DO UPDATE SET full_name = excluded.full_name, username = excluded.username',
      tgUser.id, [tgUser.first_name, tgUser.last_name].filter(Boolean).join(' '), tgUser.username ?? null, nowStr(),
    );
  }
  const fullName = user.fromSession ? user.first_name : [user.first_name, user.last_name].filter(Boolean).join(' ');
  const signedIn = Boolean(req.account);
  // Mehmon Telegram user'i avval ro'yxatdan o'tgan bo'lsa — kirish oynasida raqami tayyor turadi
  const own = !signedIn && tgUser ? accountByUser(tgUser.id) : null;
  res.json({
    user: { id: user.id, firstName: user.first_name, fullName, username: user.username, photoUrl: user.photo_url },
    account: signedIn ? publicAccount(req.account) : null,
    authHint: tgUser && !signedIn ? { registered: Boolean(own), digits: own ? own.phone.slice(3) : '' } : null,
    balance: signedIn ? balanceOf(user.id) : 0,
    isAdmin: signedIn && isAdmin(user.id),
    isOwner: signedIn && isOwner(user.id), // adminlar va huquqlarni boshqarish — faqat bot egasi
    adminPerms: signedIn ? permsOf(user.id) : [], // admin panel bo'limlari shunga qarab ochiladi
    freeOrders: signedIn && hasPerm(user.id, 'free'), // buyurtma narxi «bepul» ko'rinadi
    settings: getSettings(),
    documents: signedIn ? one('SELECT COUNT(*) AS n FROM documents WHERE user_id = ?', user.id).n : 0,
    // Tayyorlanayotgan yoki to'lovi tekshiruvdagi buyurtma — ilova ochilganda uning holatiga qaytariladi
    activeOrder: signedIn ? (waitingOrder(user.id) ?? null) : null,
    // Qo'ng'iroqchadagi qizil raqam — darhol ko'rinsin
    unreadNotifications: unreadCount(user.id),
  });
});

router.get('/balance', (req, res) => res.json({ balance: balanceOf(req.user.id) }));

// ===== Hamyon tarixi =====
router.get('/transactions', (req, res) => {
  const transactions = all(
    'SELECT id, amount, kind, note, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 30',
    req.user.id,
  );
  const pending = one(
    "SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS sum FROM payments WHERE user_id = ? AND status = 'pending'",
    req.user.id,
  );
  res.json({ balance: balanceOf(req.user.id), transactions, pending });
});

// ===== Hisobni to'ldirish — chek bot orqali yuboriladi, shuning uchun botda davom etadi =====
router.post('/topup', async (req, res) => {
  const need = Number(req.body?.need) || 0;
  const text =
    "💳 <b>Hisobni to'ldirish</b>\n\n" +
    `👛 Balans: <b>${money(balanceOf(req.user.id))}</b>\n` +
    (need > 0 ? `⭐ Buyurtma uchun yana <b>${money(need)}</b> kerak.\n` : '') +
    "\nPastdagi tugmani bosing, summani tanlang va to'lov chekini shu yerga yuboring 👇";
  try {
    await tg('sendMessage', {
      chat_id: req.user.id,
      text,
      parse_mode: 'HTML',
      reply_markup: {
        inline_keyboard: [
          [{ text: "➕ Hisobni to'ldirish", callback_data: 'wallet_topup' }],
          [{ text: '📜 Tarix', callback_data: 'wallet_history' }],
        ],
      },
    });
    res.json({ ok: true, bot: getSettings().bot_username });
  } catch (error) {
    res.status(502).json({ error: telegramReason(error) });
  }
});

// ===== Titul ma'lumotlari (bot bilan umumiy) =====
function getTitle(userId) {
  const row = one('SELECT data FROM titles WHERE user_id = ?', userId);
  try {
    return row ? JSON.parse(row.data) : {};
  } catch {
    return {};
  }
}

router.get('/title', (req, res) => res.json({ title: getTitle(req.user.id) }));

router.put('/title', (req, res) => {
  const title = {};
  for (const key of TITLE_FIELDS) {
    const value = String(req.body?.[key] ?? '').split(/\s+/).filter(Boolean).join(' ');
    if (value.length > TITLE_MAX) return res.status(400).json({ error: `${TITLE_MAX} belgidan oshmasin.` });
    if (value) title[key] = value;
  }
  run(
    'INSERT INTO titles (user_id, data) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET data = excluded.data',
    req.user.id, JSON.stringify(title),
  );
  res.json({ title });
});

// ===== Profil statistikasi =====
router.get('/stats', (req, res) => {
  const rows = all('SELECT kind, COUNT(*) AS n FROM documents WHERE user_id = ? GROUP BY kind', req.user.id);
  const spent = one(
    "SELECT COALESCE(-SUM(amount), 0) AS n FROM transactions WHERE user_id = ? AND kind IN ('charge', 'refund')",
    req.user.id,
  ).n;
  res.json({ byKind: Object.fromEntries(rows.map((r) => [r.kind, r.n])), spent, support: getSettings().support });
});

export default router;
