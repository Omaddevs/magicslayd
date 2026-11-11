// Bildirishnomalar: admin hamma userlarga xabar yuboradi — ilovada (qo'ng'iroqcha) va Telegram botda.
// Ilova: shu jadvaldan o'qiydi, kim o'qigani notification_reads da.
// Bot: bot_status = 'queued' bo'lgan xabarni barcha userlarga tarqatadi (prezentatsiya_bot/handlers/broadcast.py).
import express, { Router } from 'express';

import { hasPerm, requirePerm } from '../admins.js';
import { all, db, nowStr, one, run } from '../db.js';
import { BadInput, image, link, media, removeImage } from './news.js';

export const NOTIFY_KINDS = ['yangilik', 'aksiya', 'yangilanish', 'muhim'];
const TITLE_MAX = 120;
const BODY_MAX = 2000;
const LIST_LIMIT = 100;

db.exec(`
  CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'yangilik', title TEXT NOT NULL, body TEXT NOT NULL,
    image TEXT, button TEXT, link TEXT, to_bot INTEGER NOT NULL DEFAULT 1,
    bot_status TEXT NOT NULL DEFAULT 'none', bot_total INTEGER NOT NULL DEFAULT 0, bot_sent INTEGER NOT NULL DEFAULT 0,
    bot_failed INTEGER NOT NULL DEFAULT 0, bot_cursor INTEGER NOT NULL DEFAULT 0, created_at TEXT);
  CREATE TABLE IF NOT EXISTS notification_reads (
    user_id INTEGER NOT NULL, notification_id INTEGER NOT NULL, read_at TEXT, PRIMARY KEY (user_id, notification_id));
  CREATE INDEX IF NOT EXISTS notification_reads_n ON notification_reads (notification_id);
`);
// Botdagi /admin dan: mode = copy (istalgan xabar nusxasi) | forward; in_app = 0 — faqat botda
const notifColumns = new Set(all('PRAGMA table_info(notifications)').map((c) => c.name));
for (const [column, definition] of [['mode', "TEXT NOT NULL DEFAULT 'text'"], ['src_chat', 'INTEGER'], ['src_msg', 'INTEGER'], ['in_app', 'INTEGER NOT NULL DEFAULT 1']]) {
  if (!notifColumns.has(column)) db.exec(`ALTER TABLE notifications ADD COLUMN ${column} ${definition}`);
}

const clean = (value, max, field, required) => {
  const text = String(value ?? '').replace(/\r/g, '').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
  if (required && !text) throw new BadInput(`${field} bo'sh bo'lmasin.`);
  if (text.length > max) throw new BadInput(`${field} ${max} belgidan oshmasin.`);
  return text;
};

// Userdan oldin yuborilgan xabarlar o'qilgan hisoblanadi — yangi user 100 ta «o'qilmagan» bilan kutib olinmasin
const READ_SQL =
  '(r.user_id IS NOT NULL OR n.created_at < COALESCE((SELECT joined_at FROM users WHERE id = @uid), \'\'))';

const preview = (body) => {
  const text = body.replace(/\s+/g, ' ').trim();
  return text.length > 140 ? `${text.slice(0, 137)}…` : text;
};

const itemOut = (n, full = false) => ({
  id: n.id,
  kind: n.kind,
  title: n.title,
  ...(full ? { body: n.body } : { preview: preview(n.body) }),
  image: media(n.image),
  button: n.button || '',
  link: n.link || '',
  createdAt: n.created_at,
  read: Boolean(n.is_read),
});

export function unreadCount(userId) {
  return one(
    `SELECT COUNT(*) AS n FROM notifications n
     LEFT JOIN notification_reads r ON r.notification_id = n.id AND r.user_id = @uid
     WHERE n.in_app = 1 AND NOT ${READ_SQL}`,
    { uid: userId },
  ).n;
}

const handle = (fn) => (req, res) => {
  try {
    fn(req, res);
  } catch (error) {
    if (error instanceof BadInput) return res.status(400).json({ error: error.message });
    console.error(error);
    res.status(500).json({ error: "Serverda xato yuz berdi. Qayta urinib ko'ring." });
  }
};

const router = Router();

// ===== Userlar uchun =====
router.get('/notifications/unread-count', (req, res) => res.json({ unread: unreadCount(req.user.id) }));

router.get('/notifications', (req, res) => {
  const items = all(
    `SELECT n.*, ${READ_SQL} AS is_read FROM notifications n
     LEFT JOIN notification_reads r ON r.notification_id = n.id AND r.user_id = @uid
     WHERE n.in_app = 1
     ORDER BY n.id DESC LIMIT ${LIST_LIMIT}`,
    { uid: req.user.id },
  ).map((n) => itemOut(n));
  res.json({ items, unread: items.filter((i) => !i.read).length });
});

/** Ochilganda — o'qilgan deb belgilanadi. */
router.get('/notifications/:id(\\d+)', (req, res) => {
  const id = Number(req.params.id);
  const n = one('SELECT * FROM notifications WHERE id = ? AND (in_app = 1 OR ?)', id, hasPerm(req.user.id, 'broadcast') ? 1 : 0);
  if (!n) return res.status(404).json({ error: "Xabar topilmadi yoki o'chirilgan." });
  run('INSERT OR IGNORE INTO notification_reads (user_id, notification_id, read_at) VALUES (?, ?, ?)', req.user.id, id, nowStr());
  res.json({ item: itemOut({ ...n, is_read: 1 }, true), unread: unreadCount(req.user.id) });
});

/** O'qilgan / o'qilmagan deb belgilash. */
router.post('/notifications/:id(\\d+)/read', (req, res) => {
  const id = Number(req.params.id);
  if (!one('SELECT 1 FROM notifications WHERE id = ?', id)) return res.status(404).json({ error: 'Xabar topilmadi.' });
  if (req.body?.read === false) {
    run('DELETE FROM notification_reads WHERE user_id = ? AND notification_id = ?', req.user.id, id);
    // Userdan oldingi xabarni «o'qilmagan» qilib bo'lmaydi (u baribir o'qilgan hisoblanadi) — muhim emas
  } else {
    run('INSERT OR IGNORE INTO notification_reads (user_id, notification_id, read_at) VALUES (?, ?, ?)', req.user.id, id, nowStr());
  }
  res.json({ unread: unreadCount(req.user.id) });
});

router.post('/notifications/read-all', (req, res) => {
  run(
    `INSERT OR IGNORE INTO notification_reads (user_id, notification_id, read_at)
     SELECT ?, id, ? FROM notifications WHERE in_app = 1`,
    req.user.id, nowStr(),
  );
  res.json({ unread: 0 });
});

// ===== Admin: yuborish va statistika =====
const audience = () => one('SELECT COUNT(*) AS n FROM users').n;

const adminOut = (n) => ({
  ...itemOut({ ...n, is_read: 1 }, true),
  toBot: Boolean(n.to_bot),
  inApp: Boolean(n.in_app ?? 1),
  mode: n.mode || 'text',
  bot: { status: n.bot_status, total: n.bot_total, sent: n.bot_sent, failed: n.bot_failed },
  reads: n.reads ?? 0,
});

router.get('/admin/notifications', requirePerm('broadcast'), (req, res) => {
  const items = all(
    `SELECT n.*, (SELECT COUNT(*) FROM notification_reads r WHERE r.notification_id = n.id) AS reads
     FROM notifications n ORDER BY n.id DESC LIMIT ${LIST_LIMIT}`,
  ).map(adminOut);
  res.json({ items, audience: audience() });
});

router.get('/admin/notifications/:id(\\d+)', requirePerm('broadcast'), (req, res) => {
  const n = one(
    'SELECT n.*, (SELECT COUNT(*) FROM notification_reads r WHERE r.notification_id = n.id) AS reads FROM notifications n WHERE n.id = ?',
    Number(req.params.id),
  );
  if (!n) return res.status(404).json({ error: 'Xabar topilmadi.' });
  res.json({ item: adminOut(n), audience: audience() });
});

router.post('/admin/notifications', requirePerm('broadcast'), express.json({ limit: '20kb' }), handle((req, res) => {
  const b = req.body || {};
  const kind = NOTIFY_KINDS.includes(b.kind) ? b.kind : 'yangilik';
  const title = clean(b.title, TITLE_MAX, 'Sarlavha', true);
  const body = clean(b.body, BODY_MAX, 'Xabar matni', true);
  const pic = image(b.image);
  const target = link(b.link);
  const button = target ? clean(b.button, 30, 'Tugma matni') : '';
  const toBot = b.toBot !== false;
  const total = toBot ? audience() : 0;
  const { lastInsertRowid } = run(
    `INSERT INTO notifications (kind, title, body, image, button, link, to_bot, bot_status, bot_total, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    kind, title, body, pic, button, target, toBot ? 1 : 0, toBot ? 'queued' : 'none', total, nowStr(),
  );
  const n = one('SELECT *, 0 AS reads FROM notifications WHERE id = ?', lastInsertRowid);
  res.status(201).json({ item: adminOut(n), audience: total });
}));

/** O'chirish: ilovadan yo'qoladi, bot tarqatayotgan bo'lsa — to'xtaydi. Botda yuborilganlari qoladi. */
router.delete('/admin/notifications/:id(\\d+)', requirePerm('broadcast'), (req, res) => {
  const id = Number(req.params.id);
  const n = one('SELECT image FROM notifications WHERE id = ?', id);
  if (!n) return res.status(404).json({ error: 'Xabar topilmadi.' });
  run('DELETE FROM notification_reads WHERE notification_id = ?', id);
  run('DELETE FROM notifications WHERE id = ?', id);
  // Rasm boshqa joyda (story, reklama) ishlatilmayotgan bo'lsa — o'chiriladi
  if (n.image && !one('SELECT 1 FROM web_stories WHERE image = ? OR detail_image = ? UNION SELECT 1 FROM web_ads WHERE image = ?', n.image, n.image, n.image)) {
    removeImage(n.image);
  }
  res.json({ ok: true });
});

/** Botda tarqatishni to'xtatish (ilovada qoladi). */
router.post('/admin/notifications/:id(\\d+)/stop', requirePerm('broadcast'), (req, res) => {
  run("UPDATE notifications SET bot_status = 'cancelled' WHERE id = ? AND bot_status IN ('queued', 'sending')", Number(req.params.id));
  res.json({ ok: true });
});

export default router;
