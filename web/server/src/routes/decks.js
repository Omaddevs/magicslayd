import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import express, { Router } from 'express';

import { DECKS_DIR } from '../config.js';
import { nowStr, one, run } from '../db.js';
import { getSettings } from '../settings.js';
import { makeToken, readToken } from '../signed.js';
import { escapeHtml, telegramReason, tgSendFile } from '../telegram.js';

// Taqdimot muharriri. Loyiha bot yaratganda diskka saqlanadi (prezentatsiya_bot/presentation/storage.py),
// bu yerda tahrirlanadi, so'ng bot uni AI'siz qayta yig'adi (web_orders, kind = 'edit')

const MEDIA_TTL = 6 * 60 * 60;
const SAFE_NAME = /^[\w.-]{1,80}$/;
const KINDS = ['bullets', 'cards', 'stats', 'timeline', 'quote'];
// Bot bilan bir xil (presentation/ai.py → ITEM_LIMITS): har bir maketdagi elementlar soni
const ITEM_LIMITS = { bullets: [1, 6], cards: [2, 4], stats: [2, 4], timeline: [3, 5], quote: [0, 1] };
// slidesPerPlan: 80 slayd 1–3 rejaga bo'linsa ham saqlansin (bot har rejaga 76 tagacha slayd qo'yishi mumkin)
const LIMITS = { plans: 10, slidesPerPlan: 80, slides: 80, conclusion: 5 };
const IMAGE_MAX = 10 * 1024 * 1024;
const VIDEO_MAX = 25 * 1024 * 1024;
const MEDIA_TOTAL_MAX = 45 * 1024 * 1024; // Telegram bot yuboradigan fayl chegarasi — 50 MB
const IMPORT_MAX = 25 * 1024 * 1024;

const deckDir = (id) => path.join(DECKS_DIR, String(id));
const mediaDir = (id) => path.join(deckDir(id), 'media');
const projectFile = (id) => path.join(deckDir(id), 'deck.json');

export const isEditable = (documentId) => existsSync(projectFile(documentId));

class BadInput extends Error {}

function readProject(id) {
  try {
    return JSON.parse(readFileSync(projectFile(id), 'utf8'));
  } catch {
    return null;
  }
}

const ownDoc = (req) =>
  one("SELECT id, title FROM documents WHERE id = ? AND user_id = ? AND kind = 'pres'", Number(req.params.id), req.user.id);

function ownDeck(req) {
  const doc = ownDoc(req);
  const project = doc ? readProject(doc.id) : null;
  return project && project.user_id === req.user.id ? { id: doc.id, doc, project } : null;
}

/** Shu hujjat uchun navbatdagi yoki bajarilayotgan vazifa (edit / import). */
function activeJob(kind, userId, documentId) {
  return one(
    "SELECT id FROM web_orders WHERE kind = ? AND user_id = ? AND status IN ('pending', 'working') AND params = ?",
    kind, userId, JSON.stringify({ document_id: documentId }),
  );
}

function queueJob(kind, userId, documentId) {
  return Number(run(
    'INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, ?, ?, 0, ?)',
    userId, kind, JSON.stringify({ document_id: documentId }), nowStr(),
  ).lastInsertRowid);
}

// ===== Tekshirish va tozalash (bot normalize_slide bilan bir xil qoidalar) =====
function str(value, max, field, { required = false } = {}) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (required && !text) throw new BadInput(`${field} bo'sh bo'lmasin.`);
  if (text.length > max) throw new BadInput(`${field} ${max} belgidan oshmasin.`);
  return text;
}

function mediaName(value, id, kind) {
  if (value == null || value === '') return null;
  const name = String(value);
  if (!SAFE_NAME.test(name) || !existsSync(path.join(mediaDir(id), name))) throw new BadInput('Fayl topilmadi, qayta yuklang.');
  const video = /\.(mp4|mov|m4v)$/i.test(name);
  if ((kind === 'video') !== video) throw new BadInput("Fayl turi noto'g'ri.");
  return name;
}

function cleanSlide(raw, id, n) {
  const where = `${n}-slayd`;
  const title = str(raw.title, 150, `${where} sarlavhasi`, { required: true });
  let kind = KINDS.includes(raw.kind) ? raw.kind : 'bullets';
  let text = str(raw.text, 600, `${where} matni`);
  let items = (Array.isArray(raw.items) ? raw.items : []).slice(0, 8).map((item, i) => ({
    heading: str(item?.heading, 80, `${where}, ${i + 1}-band sarlavhasi`),
    text: str(item?.text, 400, `${where}, ${i + 1}-band matni`),
  })).filter((item) => item.heading || item.text)
    .map((item) => (item.text ? item : { heading: '', text: item.heading }));

  // Maketga elementlar yetmasa — ro'yxatga o'tkaziladi (aks holda PPTX buziladi)
  if (kind === 'quote' && !text) kind = 'bullets';
  if (!['quote', 'bullets'].includes(kind) && items.length < ITEM_LIMITS[kind][0]) kind = 'bullets';
  if (kind === 'bullets' && !items.length) {
    items = [{ heading: '', text: text || title }];
    text = '';
  }
  const video = mediaName(raw.video, id, 'video');
  return {
    title, kind, text, items: items.slice(0, ITEM_LIMITS[kind][1]),
    image: video ? null : mediaName(raw.image, id, 'image'), video,
  };
}

function cleanContent(raw, id) {
  if (!raw || !Array.isArray(raw.plans)) throw new BadInput("Taqdimot ma'lumoti buzilgan.");
  if (!raw.plans.length || raw.plans.length > LIMITS.plans) throw new BadInput(`Rejalar soni 1–${LIMITS.plans} ta bo'lsin.`);
  let n = 3; // muqova, mundarija, reja
  const plans = raw.plans.map((plan, p) => {
    const slides = Array.isArray(plan?.slides) ? plan.slides : [];
    if (!slides.length) throw new BadInput(`${p + 1}-rejada kamida bitta slayd bo'lsin.`);
    if (slides.length > LIMITS.slidesPerPlan) throw new BadInput(`Bitta rejada ${LIMITS.slidesPerPlan} tadan ko'p slayd bo'lmasin.`);
    return {
      title: str(plan.title, 120, `${p + 1}-reja nomi`, { required: true }),
      slides: slides.map((slide) => cleanSlide(slide ?? {}, id, ++n)),
    };
  });
  if (n - 3 > LIMITS.slides) throw new BadInput(`Slaydlar ${LIMITS.slides} tadan oshmasin.`);
  const conclusion = (Array.isArray(raw.conclusion) ? raw.conclusion : [])
    .map((point, i) => str(point, 300, `Xulosaning ${i + 1}-bandi`)).filter(Boolean).slice(0, LIMITS.conclusion);
  return {
    title: str(raw.title, 200, 'Taqdimot nomi', { required: true }),
    subtitle: str(raw.subtitle, 300, 'Kichik sarlavha'),
    cover_image: mediaName(raw.cover_image, id, 'image'),
    plans,
    conclusion: conclusion.length ? conclusion : ['—'],
  };
}

function usedMedia(content) {
  const names = new Set([content.cover_image]);
  for (const plan of content.plans) for (const slide of plan.slides) names.add(slide.image).add(slide.video);
  names.delete(null);
  return names;
}

// ===== Routelar (Authorization bilan) =====
const router = Router();

router.get('/decks/:id(\\d+)', (req, res) => {
  const deck = ownDeck(req);
  if (!deck) {
    const doc = ownDoc(req);
    if (!doc) return res.status(404).json({ error: 'Taqdimot topilmadi.' });
    // Loyihasi yo'q (eski taqdimot) — fayldan tiklash mumkin: POST /decks/:id/import
    return res.status(404).json({
      error: 'Taqdimot hali tahrirlashga tayyorlanmagan.',
      importable: true,
      pendingImport: activeJob('import', req.user.id, doc.id)?.id ?? null,
    });
  }
  const { project } = deck;
  const pending = activeJob('edit', req.user.id, deck.id);
  res.json({
    id: deck.id,
    theme: project.theme,
    lang: project.lang,
    author: project.author ?? '',
    content: project.content,
    mediaToken: makeToken(['media', deck.id, req.user.id], MEDIA_TTL),
    pendingOrder: pending?.id ?? null,
    imported: Boolean(project.imported),
    limits: { ...LIMITS, items: ITEM_LIMITS, imageMax: IMAGE_MAX, videoMax: VIDEO_MAX },
  });
});

// Saqlash: loyiha yoziladi va bot qayta yig'ish uchun navbatga qo'yiladi
router.put('/decks/:id(\\d+)', express.json({ limit: '1mb' }), (req, res) => {
  const deck = ownDeck(req);
  if (!deck) return res.status(404).json({ error: 'Taqdimot topilmadi.' });
  let content;
  let author;
  try {
    content = cleanContent(req.body?.content, deck.id);
    author = str(req.body?.author, 70, 'Muallif ismi');
  } catch (error) {
    if (error instanceof BadInput) return res.status(400).json({ error: error.message });
    throw error;
  }
  const theme = req.body?.theme in getSettings().themes ? req.body.theme : deck.project.theme;

  const used = usedMedia(content);
  const total = [...used].reduce((sum, name) => sum + statSync(path.join(mediaDir(deck.id), name)).size, 0);
  if (total > MEDIA_TOTAL_MAX) {
    return res.status(413).json({ error: 'Rasm va videolar jami 45 MB dan oshmasin. Videoni qisqaroq qiling.' });
  }

  const project = { ...deck.project, theme, author, content };
  // Avval vaqtinchalik faylga — yozish yarim qolsa ham loyiha buzilmaydi
  const temp = `${projectFile(deck.id)}.${process.pid}.tmp`;
  writeFileSync(temp, JSON.stringify(project));
  renameSync(temp, projectFile(deck.id));
  run('UPDATE documents SET title = ? WHERE id = ?', content.title, deck.id);

  // Endi ishlatilmayotgan media fayllar o'chiriladi
  for (const name of readdirSync(mediaDir(deck.id))) {
    if (!used.has(name) && !name.endsWith('.tmp')) {
      try {
        unlinkSync(path.join(mediaDir(deck.id), name));
      } catch {
        // band bo'lsa — keyingi saqlashda o'chadi
      }
    }
  }

  const pending = one(
    "SELECT id FROM web_orders WHERE kind = 'edit' AND user_id = ? AND status = 'pending' AND params = ?",
    req.user.id, JSON.stringify({ document_id: deck.id }),
  );
  // Navbatda turgan bo'lsa — yangisi kerak emas: bot baribir eng oxirgi deck.json ni yig'adi
  res.json({ orderId: pending?.id ?? queueJob('edit', req.user.id, deck.id) });
});

// Eski taqdimot (loyihasi saqlanmagan) — bot fayldan loyihani tiklaydi
router.post('/decks/:id(\\d+)/import', (req, res) => {
  const doc = ownDoc(req);
  if (!doc) return res.status(404).json({ error: 'Taqdimot topilmadi.' });
  if (isEditable(doc.id)) return res.json({ orderId: null, ready: true });
  res.json({ orderId: activeJob('import', req.user.id, doc.id)?.id ?? queueJob('import', req.user.id, doc.id) });
});

// O'z faylini (PPTX yoki PDF) yuklab tahrirlash. Fayl chatga ham yuboriladi va «Saqlangan» ga qo'shiladi
router.post('/imports', express.raw({ type: () => true, limit: IMPORT_MAX }), async (req, res) => {
  const data = req.body;
  if (!Buffer.isBuffer(data) || !data.length) return res.status(400).json({ error: "Fayl bo'sh." });
  let ext = null;
  if (data.subarray(0, 4).toString('latin1') === '%PDF') ext = 'pdf';
  else if (data.subarray(0, 2).toString('latin1') === 'PK' && data.includes('ppt/')) ext = 'pptx';
  else if (data.subarray(0, 4).equals(Buffer.from([0xd0, 0xcf, 0x11, 0xe0]))) {
    return res.status(415).json({ error: "Bu eski .ppt formati. PowerPoint'da «.pptx» qilib saqlab, qayta yuklang." });
  }
  if (!ext) return res.status(415).json({ error: 'Faqat PPTX yoki PDF fayl yuklash mumkin.' });

  let name = 'Taqdimot';
  try {
    name = decodeURIComponent(req.get('X-File-Name') || '').replace(/\.(pptx|pdf)$/i, '').replace(/\s+/g, ' ').trim() || name;
  } catch {
    // noto'g'ri kodlangan nom — standart nom qoladi
  }
  const title = name.slice(0, 150);
  try {
    // Chatga yuborish file_id beradi — fayl botdagi «📂 Hujjatlarim» da ham ko'rinadi
    const fileId = await tgSendFile(req.user.id, data, `${title}.${ext}`, `📥 ${escapeHtml(title)}\n✏️ Saytda tahrirlash uchun yuklandi`);
    const documentId = Number(run(
      "INSERT INTO documents (user_id, kind, title, file_id, created_at) VALUES (?, 'pres', ?, ?, ?)",
      req.user.id, title, fileId, nowStr(),
    ).lastInsertRowid);
    mkdirSync(deckDir(documentId), { recursive: true });
    writeFileSync(path.join(deckDir(documentId), `source.${ext}`), data);
    res.status(201).json({ documentId, orderId: queueJob('import', req.user.id, documentId) });
  } catch (error) {
    res.status(502).json({ error: telegramReason(error) });
  }
});

// Rasm yoki video yuklash (xom fayl, Content-Type bilan). Fayl turi ichidan tekshiriladi
router.post('/decks/:id(\\d+)/media', express.raw({ type: () => true, limit: VIDEO_MAX }), (req, res) => {
  const deck = ownDeck(req);
  if (!deck) return res.status(404).json({ error: 'Taqdimot topilmadi.' });
  const data = req.body;
  if (!Buffer.isBuffer(data) || !data.length) return res.status(400).json({ error: "Fayl bo'sh." });

  let ext = null;
  if (data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) ext = 'jpg';
  else if (data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) ext = 'png';
  else if (data.subarray(4, 8).toString('latin1') === 'ftyp') ext = data.subarray(8, 10).toString('latin1') === 'qt' ? 'mov' : 'mp4';
  if (!ext) return res.status(415).json({ error: 'Faqat JPG/PNG rasm yoki MP4/MOV video yuklash mumkin.' });

  const video = ext === 'mp4' || ext === 'mov';
  if (!video && data.length > IMAGE_MAX) return res.status(413).json({ error: 'Rasm 10 MB dan oshmasin.' });
  mkdirSync(mediaDir(deck.id), { recursive: true });
  const name = `${video ? 'video' : 'img'}-${randomUUID().slice(0, 12)}.${ext}`;
  writeFileSync(path.join(mediaDir(deck.id), name), data);
  res.status(201).json({ name, kind: video ? 'video' : 'image' });
});

// ===== Media fayllarni ko'rsatish (imzolangan havola, <img>/<video> uchun) =====
export const mediaRouter = Router();

mediaRouter.get('/media/:token/:name', (req, res) => {
  const parts = readToken(req.params.token);
  const { name } = req.params;
  if (!parts || parts[0] !== 'media' || !SAFE_NAME.test(name)) return res.status(403).end();
  const file = path.join(mediaDir(Number(parts[1])), name);
  if (!existsSync(file)) return res.status(404).end();
  // sendFile Range so'rovlarini qo'llaydi — video telefonda bo'laklab yuklanadi
  res.sendFile(file, { maxAge: '1h', headers: { 'X-Content-Type-Options': 'nosniff' } });
});

export default router;
