import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import express, { Router } from 'express';

import { adminIds, isAdmin, requirePerm } from '../admins.js';

const canBroadcast = requirePerm('broadcast'); // yangilik, story, reklama — «📣 Xabar tarqatish» huquqi
import { DB_PATH } from '../config.js';
import { all, db, nowStr, one, run } from '../db.js';
import { escapeHtml, telegramReason, tg } from '../telegram.js';

// Bosh sahifadagi «Yangiliklar (Story)» va reklama bannerlari.
// Hamma ko'radi; qo'shish va o'chirish — faqat adminlar (bot egasi va u qo'shganlar — admins.js).
// Rasmlar <DATA_DIR>/news/ da, tasodifiy nom bilan; /api/news-media/<nom> orqali ochiq beriladi (initData'siz — <img> uchun).

export const NEWS_DIR = path.join(path.dirname(DB_PATH), 'news');
const IMAGE_MAX = 8 * 1024 * 1024;
const IMAGE_NAME = /^news-[a-f0-9-]{12}\.(jpg|png)$/;
const STORY_KINDS = ['yangilanish', 'blog', 'aksiya', 'qollanma', 'yangilik'];
const AD_COLORS = ['purple', 'blue', 'orange', 'green', 'pink', 'dark'];
// Ilova ichidagi manzillar (tugma bosilganda ochiladi) — client: components/News.jsx → openTarget
const APP_LINKS = ['pres', 'referat', 'kurs', 'mustaqil', 'diploma', 'dissertation', 'ai', 'templates', 'topup', 'materials'];
const MAX_STORIES = 30;
const MAX_ADS = 10;

db.exec(`
  CREATE TABLE IF NOT EXISTS web_stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, title TEXT NOT NULL, text TEXT, image TEXT,
    button TEXT, link TEXT, created_at TEXT);
  CREATE TABLE IF NOT EXISTS web_ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, text TEXT, image TEXT, button TEXT, link TEXT,
    color TEXT NOT NULL DEFAULT 'purple', created_at TEXT);
  CREATE TABLE IF NOT EXISTS web_story_likes (
    story_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TEXT, PRIMARY KEY (story_id, user_id));
`);
// Story'ning yangi maydonlari: badge — tepadagi yorliq, points — ✓ bandlar (JSON),
// details / detail_image — «Batafsil» bosilganda ochiladigan reklama sahifasi
const storyColumns = new Set(all('PRAGMA table_info(web_stories)').map((c) => c.name));
for (const column of ['badge', 'points', 'details', 'detail_image']) {
  if (!storyColumns.has(column)) db.exec(`ALTER TABLE web_stories ADD COLUMN ${column} TEXT`);
}
const REPLY_GAP_MS = 20_000; // bitta user — 20 soniyada bitta xabar
const lastReply = new Map();

export class BadInput extends Error {}

const str = (value, max, field, { required = false } = {}) => {
  const text = String(value ?? '').replace(/[ \t]+/g, ' ').trim();
  if (required && !text) throw new BadInput(`${field} bo'sh bo'lmasin.`);
  if (text.length > max) throw new BadInput(`${field} ${max} belgidan oshmasin.`);
  return text;
};

export function image(value) {
  const name = String(value ?? '').trim();
  if (!name) return null;
  if (!IMAGE_NAME.test(name) || !existsSync(path.join(NEWS_DIR, name))) throw new BadInput('Rasm topilmadi — qayta yuklang.');
  return name;
}

export function link(value) {
  const text = String(value ?? '').trim();
  if (!text) return '';
  if (text.startsWith('app:') && APP_LINKS.includes(text.slice(4))) return text;
  if (/^https:\/\/[^\s]{3,490}$/.test(text) || /^https:\/\/t\.me\/[\w/+-]{2,100}$/.test(text)) return text;
  throw new BadInput("Havola noto'g'ri: https:// bilan boshlansin yoki ilova bo'limini tanlang.");
}

export function removeImage(name) {
  if (!name || !IMAGE_NAME.test(name)) return;
  try {
    unlinkSync(path.join(NEWS_DIR, name));
  } catch {
    // fayl allaqachon yo'q — muhim emas
  }
}

export const media = (name) => (name ? `/api/news-media/${name}` : null);
function parsePoints(value) {
  try {
    const list = JSON.parse(value || '[]');
    return Array.isArray(list) ? list.map(String) : [];
  } catch {
    return [];
  }
}
const storyOut = (s) => ({ id: s.id, kind: s.kind, title: s.title || '', text: s.text || '', image: media(s.image),
  button: s.button || '', link: s.link || '', badge: s.badge || '', points: parsePoints(s.points),
  details: s.details || '', detailImage: media(s.detail_image), likes: s.likes ?? 0, liked: Boolean(s.liked),
  createdAt: s.created_at });
const adOut = (a) => ({ id: a.id, title: a.title || '', text: a.text || '', image: media(a.image), button: a.button || '',
  link: a.link || '', color: a.color, createdAt: a.created_at });

export function adminOnly(req, res, next) {
  if (isAdmin(req.user?.id)) return next();
  return res.status(403).json({ error: 'Faqat admin uchun.' });
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

// ===== Ochiq: rasmlar =====
export const newsMediaRouter = Router();
newsMediaRouter.get('/news-media/:name', (req, res) => {
  const { name } = req.params;
  if (!IMAGE_NAME.test(name)) return res.status(404).end();
  const file = path.join(NEWS_DIR, name);
  if (!existsSync(file)) return res.status(404).end();
  res.setHeader('Cache-Control', 'public, max-age=31536000, immutable'); // nom tasodifiy — o'zgarmaydi
  res.sendFile(file);
});

// ===== initData bilan =====
const router = Router();

router.get('/news', (req, res) => {
  res.json({
    stories: all(
      'SELECT s.*, (SELECT COUNT(*) FROM web_story_likes l WHERE l.story_id = s.id) AS likes, ' +
        'EXISTS (SELECT 1 FROM web_story_likes l WHERE l.story_id = s.id AND l.user_id = ?) AS liked ' +
        `FROM web_stories s ORDER BY s.id DESC LIMIT ${MAX_STORIES}`,
      req.account ? req.user.id : 0,
    ).map(storyOut),
    ads: all(`SELECT * FROM web_ads ORDER BY id ASC LIMIT ${MAX_ADS}`).map(adOut),
  });
});

router.post('/news/media', canBroadcast, express.raw({ type: () => true, limit: IMAGE_MAX }), (req, res) => {
  const data = req.body;
  if (!Buffer.isBuffer(data) || !data.length) return res.status(400).json({ error: "Fayl bo'sh." });
  let ext = null;
  if (data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) ext = 'jpg';
  else if (data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) ext = 'png';
  if (!ext) return res.status(415).json({ error: 'Faqat JPG yoki PNG rasm yuklash mumkin.' });
  mkdirSync(NEWS_DIR, { recursive: true });
  const name = `news-${randomUUID().slice(0, 12)}.${ext}`;
  writeFileSync(path.join(NEWS_DIR, name), data);
  res.status(201).json({ name, url: media(name) });
});

router.post('/news/stories', canBroadcast, handle((req, res) => {
  const b = req.body || {};
  const kind = STORY_KINDS.includes(b.kind) ? b.kind : 'yangilik';
  const points = (Array.isArray(b.points) ? b.points : [])
    .map((p, i) => str(p, 60, `${i + 1}-band`)).filter(Boolean).slice(0, 4);
  const story = {
    title: str(b.title, 80, 'Sarlavha'),
    text: str(b.text, 300, 'Qisqa matn'),
    image: image(b.image),
    badge: str(b.badge, 30, 'Yorliq'),
    details: str(b.details, 4000, 'Batafsil matn'),
    detailImage: image(b.detailImage),
    button: str(b.button, 30, 'Tugma matni'),
    link: link(b.link),
  };
  // Sarlavhasiz story — faqat tayyor afisha (rasm) bo'lsa
  if (!story.title && !story.image) throw new BadInput('Sarlavha yozing yoki afisha rasmini yuklang.');
  if (story.link && !story.button) story.button = 'Batafsil';
  const result = run(
    'INSERT INTO web_stories (kind, title, text, image, button, link, badge, points, details, detail_image, created_at) ' +
      'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    kind, story.title, story.text, story.image, story.button, story.link, story.badge, JSON.stringify(points),
    story.details, story.detailImage, nowStr(),
  );
  // Juda eskilari (ro'yxatdan chiqib ketganlari) rasmi bilan o'chadi
  for (const old of all(`SELECT id, image, detail_image FROM web_stories ORDER BY id DESC LIMIT -1 OFFSET ${MAX_STORIES}`)) {
    deleteStory(old);
  }
  res.status(201).json({ story: storyOut(one('SELECT * FROM web_stories WHERE id = ?', result.lastInsertRowid)) });
}));

function deleteStory(row) {
  run('DELETE FROM web_stories WHERE id = ?', row.id);
  run('DELETE FROM web_story_likes WHERE story_id = ?', row.id);
  removeImage(row.image);
  removeImage(row.detail_image);
}

router.delete('/news/stories/:id(\\d+)', canBroadcast, (req, res) => {
  const row = one('SELECT id, image, detail_image FROM web_stories WHERE id = ?', Number(req.params.id));
  if (!row) return res.status(404).json({ error: 'Topilmadi.' });
  deleteStory(row);
  res.json({ ok: true });
});

// Yurakcha — har bir user uchun bitta (qayta bosilsa olib tashlanadi)
router.post('/news/stories/:id(\\d+)/like', (req, res) => {
  const id = Number(req.params.id);
  if (!one('SELECT 1 FROM web_stories WHERE id = ?', id)) return res.status(404).json({ error: 'Topilmadi.' });
  const removed = run('DELETE FROM web_story_likes WHERE story_id = ? AND user_id = ?', id, req.user.id).changes;
  if (!removed) run('INSERT INTO web_story_likes (story_id, user_id, created_at) VALUES (?, ?, ?)', id, req.user.id, nowStr());
  res.json({ liked: !removed, likes: one('SELECT COUNT(*) AS n FROM web_story_likes WHERE story_id = ?', id).n });
});

// «Xabar yuborish» — adminning Telegram chatiga keladi (kim yozgani bilan)
router.post('/news/stories/:id(\\d+)/reply', async (req, res) => {
  const story = one('SELECT id, title, kind FROM web_stories WHERE id = ?', Number(req.params.id));
  if (!story) return res.status(404).json({ error: 'Topilmadi.' });
  if (!adminIds().length) return res.status(503).json({ error: 'Hozircha xabar yuborib bo\'lmaydi.' });
  const text = String(req.body?.text ?? '').trim().slice(0, 1000);
  if (!text) return res.status(400).json({ error: "Xabar bo'sh." });
  const now = Date.now();
  if (now - (lastReply.get(req.user.id) || 0) < REPLY_GAP_MS) {
    return res.status(429).json({ error: 'Biroz kutib, keyin yana yozing.' });
  }
  lastReply.set(req.user.id, now);
  const u = req.user;
  const name = [u.first_name, u.last_name].filter(Boolean).join(' ') || 'Foydalanuvchi';
  const who = `<a href="tg://user?id=${u.id}">${escapeHtml(name)}</a>${u.username ? ` (@${escapeHtml(u.username)})` : ''} · <code>${u.id}</code>`;
  // Barcha adminlarga; kamida bittasiga yetsa — yuborildi
  const results = await Promise.allSettled(adminIds('broadcast').map((chatId) => tg('sendMessage', {
    chat_id: chatId,
    parse_mode: 'HTML',
    text: `💬 <b>Story'ga javob</b>\n📰 ${escapeHtml(story.title || 'Afisha')}\n👤 ${who}\n\n${escapeHtml(text)}`,
  })));
  const delivered = results.some((r) => r.status === 'fulfilled');
  try {
    if (!delivered) throw results[0]?.reason ?? new Error('Yuborilmadi');
    res.json({ ok: true });
  } catch (error) {
    lastReply.delete(req.user.id);
    res.status(502).json({ error: telegramReason(error) });
  }
});

router.post('/news/ads', canBroadcast, handle((req, res) => {
  if (one('SELECT COUNT(*) AS n FROM web_ads').n >= MAX_ADS) throw new BadInput(`Ko'pi bilan ${MAX_ADS} ta reklama. Avval eskisini o'chiring.`);
  const b = req.body || {};
  const ad = {
    title: str(b.title, 70, 'Sarlavha'),
    text: str(b.text, 140, 'Matn'),
    image: image(b.image),
    button: str(b.button, 30, 'Tugma matni'),
    link: link(b.link),
    color: AD_COLORS.includes(b.color) ? b.color : 'purple',
  };
  if (!ad.title && !ad.image) throw new BadInput('Sarlavha yozing yoki rasm yuklang.');
  const result = run(
    'INSERT INTO web_ads (title, text, image, button, link, color, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
    ad.title, ad.text, ad.image, ad.button, ad.link, ad.color, nowStr(),
  );
  res.status(201).json({ ad: adOut(one('SELECT * FROM web_ads WHERE id = ?', result.lastInsertRowid)) });
}));

router.delete('/news/ads/:id(\\d+)', canBroadcast, (req, res) => {
  const row = one('SELECT id, image FROM web_ads WHERE id = ?', Number(req.params.id));
  if (!row) return res.status(404).json({ error: 'Topilmadi.' });
  run('DELETE FROM web_ads WHERE id = ?', row.id);
  removeImage(row.image);
  res.json({ ok: true });
});

export default router;
