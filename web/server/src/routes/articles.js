import { randomUUID } from 'node:crypto';
import {
  cpSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, statSync, unlinkSync, writeFileSync,
} from 'node:fs';
import path from 'node:path';

import express, { Router } from 'express';

import { ARTICLES_DIR } from '../config.js';
import { nowStr, one, run } from '../db.js';
import { makeToken, readToken } from '../signed.js';
import { escapeHtml, telegramReason, tgSendFile } from '../telegram.js';
import { fileName } from './download.js';

// Maqola muharriri. Loyiha bot yozganda saqlanadi (prezentatsiya_bot/articles/storage.py), bu yerda avtomatik
// saqlanadi (har bir o'zgarish — yangi versiya, oxirgi 10 tasi qoladi). Word/PDF faqat so'ralganda bot tomonidan
// JORIY versiyadan yasaladi (web_orders, kind = 'edit', params: { document_id, fmt })

const MEDIA_TTL = 6 * 60 * 60;
const LINK_TTL = 10 * 60;
const SAFE_NAME = /^[\w.-]{1,80}$/;
const COLOR = /^#[0-9a-fA-F]{6}$/;
const LINK = /^(https?:\/\/|mailto:)[^\s<>"']{1,500}$/;
const ALIGNS = ['left', 'center', 'right', 'justify'];
const LIMITS = { blocks: 400, runs: 200, text: 8000, items: 60, rows: 40, cols: 8, caption: 300, title: 300, author: 200 };
const IMAGE_MAX = 10 * 1024 * 1024;
const MEDIA_TOTAL_MAX = 60 * 1024 * 1024;
const VERSIONS_KEEP = 10;
const MIME = {
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
};

const articleDir = (id) => path.join(ARTICLES_DIR, String(id));
const mediaDir = (id) => path.join(articleDir(id), 'media');
const projectFile = (id) => path.join(articleDir(id), 'article.json');

export const isArticle = (documentId) => existsSync(projectFile(documentId));

class BadInput extends Error {}

function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

function writeJson(file, data) {
  const temp = `${file}.${process.pid}.tmp`;
  writeFileSync(temp, JSON.stringify(data));
  renameSync(temp, file); // yozish yarim qolsa ham eski fayl buzilmaydi
}

const ownDoc = (req) =>
  one("SELECT id, title, file_id FROM documents WHERE id = ? AND user_id = ? AND kind = 'maqola'", Number(req.params.id), req.user.id);

/** Faqat egasi: hujjat bazada shu userniki va loyiha ichidagi user_id ham mos. */
function ownArticle(req) {
  const doc = ownDoc(req);
  const project = doc ? readJson(projectFile(doc.id)) : null;
  return project && project.user_id === req.user.id ? { id: doc.id, doc, project } : null;
}

// ===== Tekshirish (bot: articles/model.py → normalize bilan bir xil qoidalar) =====
function runsOf(raw) {
  const out = [];
  for (const run of (Array.isArray(raw) ? raw : []).slice(0, LIMITS.runs)) {
    if (!run || typeof run !== 'object') continue;
    const text = String(run.text ?? '').slice(0, LIMITS.text);
    if (!text) continue;
    const clean = { text };
    for (const key of ['b', 'i', 'u']) if (run[key]) clean[key] = 1;
    if (typeof run.color === 'string' && COLOR.test(run.color)) clean.color = run.color.toLowerCase();
    if (Number.isFinite(run.size) && run.size >= 8 && run.size <= 40) clean.size = Math.round(run.size);
    if (typeof run.link === 'string' && LINK.test(run.link)) clean.link = run.link;
    out.push(clean);
  }
  return out;
}

const alignOf = (value, fallback = 'left') => (ALIGNS.includes(value) ? value : fallback);

function cleanBlocks(raw, id) {
  if (!Array.isArray(raw)) throw new BadInput("Maqola ma'lumoti buzilgan.");
  if (raw.length > LIMITS.blocks) throw new BadInput(`Maqolada ${LIMITS.blocks} tadan ko'p blok bo'lmasin.`);
  const out = [];
  for (const block of raw) {
    if (!block || typeof block !== 'object') continue;
    if (block.t === 'h' || block.t === 'p') {
      const runs = runsOf(block.runs);
      if (!runs.length) continue;
      if (block.t === 'h') out.push({ t: 'h', level: [1, 2, 3].includes(block.level) ? block.level : 2, align: alignOf(block.align), runs });
      else out.push({ t: 'p', align: alignOf(block.align, 'justify'), runs });
    } else if (block.t === 'ul' || block.t === 'ol') {
      const items = (Array.isArray(block.items) ? block.items : []).slice(0, LIMITS.items).map(runsOf).filter((r) => r.length);
      if (items.length) out.push({ t: block.t, items });
    } else if (block.t === 'table') {
      const rows = (Array.isArray(block.rows) ? block.rows : []).slice(0, LIMITS.rows)
        .filter((row) => Array.isArray(row) && row.length)
        .map((row) => row.slice(0, LIMITS.cols).map(runsOf));
      if (!rows.length) continue;
      const width = Math.max(...rows.map((r) => r.length));
      out.push({ t: 'table', head: Boolean(block.head), rows: rows.map((r) => [...r, ...Array(width - r.length).fill([])]) });
    } else if (block.t === 'img') {
      const src = String(block.src ?? '');
      if (!SAFE_NAME.test(src) || !existsSync(path.join(mediaDir(id), src))) throw new BadInput('Rasm topilmadi, qayta yuklang.');
      const width = Number(block.width);
      out.push({
        t: 'img', src,
        width: Number.isFinite(width) && width >= 25 && width <= 100 ? Math.round(width) : 80,
        align: ['left', 'center', 'right'].includes(block.align) ? block.align : 'center',
        caption: String(block.caption ?? '').replace(/\s+/g, ' ').trim().slice(0, LIMITS.caption),
      });
    }
  }
  return out;
}

function cleanText(value, max, field, required = false) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (required && !text) throw new BadInput(`${field} bo'sh bo'lmasin.`);
  if (text.length > max) throw new BadInput(`${field} ${max} belgidan oshmasin.`);
  return text;
}

/** Shu hujjat uchun eksport vazifasi (navbatda yoki bajarilmoqda). */
const exportJob = (userId, id, fmt) => one(
  "SELECT id FROM web_orders WHERE kind = 'edit' AND user_id = ? AND status IN ('pending', 'working') AND params = ?",
  userId, JSON.stringify({ document_id: id, fmt }),
);

/** Joriy versiyadan yasalgan fayl bormi. */
function freshExport(id, project, fmt) {
  const meta = readJson(path.join(articleDir(id), 'export.json')) ?? {};
  const file = path.join(articleDir(id), `file.${fmt}`);
  return meta[fmt] === project.rev && existsSync(file) ? file : null;
}

function publicProject(id, project, userId) {
  return {
    id,
    rev: project.rev,
    title: project.title,
    author: project.author ?? '',
    blocks: project.blocks,
    params: project.params,
    notice: project.notice ?? '',
    updatedAt: project.updated_at,
    mediaToken: makeToken(['amedia', id, userId], MEDIA_TTL),
    hasOriginal: existsSync(path.join(articleDir(id), 'original.json')),
    limits: { ...LIMITS, imageMax: IMAGE_MAX },
  };
}

function saveVersion(id, project) {
  const dir = path.join(articleDir(id), 'versions');
  mkdirSync(dir, { recursive: true });
  writeJson(path.join(dir, `${project.rev}.json`), { rev: project.rev, title: project.title, author: project.author ?? '', blocks: project.blocks, saved_at: project.updated_at });
  const old = readdirSync(dir).map((n) => Number.parseInt(n, 10)).filter(Number.isFinite).sort((a, b) => b - a).slice(VERSIONS_KEEP);
  for (const rev of old) {
    try {
      unlinkSync(path.join(dir, `${rev}.json`));
    } catch {
      // band bo'lsa — keyingi saqlashda o'chadi
    }
  }
}

// ===== Routelar (Authorization bilan) =====
const router = Router();
// /api/articles/ umumiy JSON o'quvchidan tashqarida (index.js → ownBody) — kichik so'rovlar uchun o'zimiz o'qiymiz
const small = express.json({ limit: '10kb' });

router.get('/articles/:id(\\d+)', (req, res) => {
  const article = ownArticle(req);
  if (!article) return res.status(404).json({ error: 'Maqola topilmadi.' });
  res.json(publicProject(article.id, article.project, req.user.id));
});

/** Avtomatik saqlash. baseRev — muharrir qaysi versiyadan tahrirlagan; boshqa joyda saqlangan bo'lsa — 409. */
router.put('/articles/:id(\\d+)', express.json({ limit: '3mb' }), (req, res) => {
  const article = ownArticle(req);
  if (!article) return res.status(404).json({ error: 'Maqola topilmadi.' });
  const { project } = article;
  if (!req.body?.force && Number(req.body?.baseRev) !== project.rev) {
    return res.status(409).json({
      error: "Maqola boshqa oynada o'zgartirilgan. Oxirgi versiya yuklandi.", conflict: true,
      article: publicProject(article.id, project, req.user.id),
    });
  }
  let blocks;
  let title;
  let author;
  try {
    title = cleanText(req.body?.title, LIMITS.title, 'Sarlavha', true);
    author = cleanText(req.body?.author, LIMITS.author, 'Muallif');
    blocks = cleanBlocks(req.body?.blocks, article.id);
  } catch (error) {
    if (error instanceof BadInput) return res.status(400).json({ error: error.message });
    throw error;
  }
  const next = { ...project, title, author, blocks, rev: project.rev + 1, updated_at: nowStr() };
  writeJson(projectFile(article.id), next);
  saveVersion(article.id, next);
  run('UPDATE documents SET title = ? WHERE id = ?', title, article.id);
  res.json({ rev: next.rev, updatedAt: next.updated_at });
});

/** AI yozgan dastlabki versiyaga qaytarish (joriy versiya tarixda qoladi). */
router.post('/articles/:id(\\d+)/restore', (req, res) => {
  const article = ownArticle(req);
  if (!article) return res.status(404).json({ error: 'Maqola topilmadi.' });
  const original = readJson(path.join(articleDir(article.id), 'original.json'));
  if (!original) return res.status(404).json({ error: 'Dastlabki versiya topilmadi.' });
  saveVersion(article.id, article.project);
  const next = { ...article.project, title: original.title, blocks: original.blocks, rev: article.project.rev + 1, updated_at: nowStr() };
  writeJson(projectFile(article.id), next);
  run('UPDATE documents SET title = ? WHERE id = ?', next.title, article.id);
  res.json(publicProject(article.id, next, req.user.id));
});

// Rasm yuklash (xom fayl, turi ichidan tekshiriladi — Word va PDF faqat JPG/PNG ni ishonchli ko'rsatadi)
router.post('/articles/:id(\\d+)/media', express.raw({ type: () => true, limit: IMAGE_MAX }), (req, res) => {
  const article = ownArticle(req);
  if (!article) return res.status(404).json({ error: 'Maqola topilmadi.' });
  const data = req.body;
  if (!Buffer.isBuffer(data) || !data.length) return res.status(400).json({ error: "Fayl bo'sh." });
  let ext = null;
  if (data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) ext = 'jpg';
  else if (data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) ext = 'png';
  if (!ext) return res.status(415).json({ error: 'Faqat JPG yoki PNG rasm yuklash mumkin.' });
  mkdirSync(mediaDir(article.id), { recursive: true });
  const used = readdirSync(mediaDir(article.id)).reduce((sum, name) => sum + statSync(path.join(mediaDir(article.id), name)).size, 0);
  if (used + data.length > MEDIA_TOTAL_MAX) return res.status(413).json({ error: "Maqoladagi rasmlar jami 60 MB dan oshmasin." });
  const name = `img-${randomUUID().slice(0, 12)}.${ext}`;
  writeFileSync(path.join(mediaDir(article.id), name), data);
  res.status(201).json({ name });
});

/** Word/PDF ni joriy versiyadan tayyorlash: tayyor bo'lsa { ready: true }, aks holda bot vazifasi { orderId }. */
router.post('/articles/:id(\\d+)/export', small, (req, res) => {
  const article = ownArticle(req);
  if (!article) return res.status(404).json({ error: 'Maqola topilmadi.' });
  const fmt = req.body?.fmt === 'pdf' ? 'pdf' : 'docx';
  if (freshExport(article.id, article.project, fmt)) return res.json({ ready: true });
  const pending = exportJob(req.user.id, article.id, fmt);
  const orderId = pending?.id ?? Number(run(
    "INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, 'edit', ?, 0, ?)",
    req.user.id, JSON.stringify({ document_id: article.id, fmt }), nowStr(),
  ).lastInsertRowid);
  res.json({ orderId });
});

function readyFile(req, res) {
  const article = ownArticle(req);
  if (!article) {
    res.status(404).json({ error: 'Maqola topilmadi.' });
    return null;
  }
  const fmt = req.body?.fmt === 'pdf' ? 'pdf' : 'docx';
  const file = freshExport(article.id, article.project, fmt);
  if (!file) {
    res.status(409).json({ error: 'Fayl hali tayyor emas. Qayta urinib ko\'ring.', stale: true });
    return null;
  }
  return { article, fmt, file };
}

router.post('/articles/:id(\\d+)/link', small, (req, res) => {
  const ready = readyFile(req, res);
  if (!ready) return;
  const { article, fmt } = ready;
  res.json({
    url: `/api/article-file/${makeToken(['afile', article.id, req.user.id, fmt], LINK_TTL)}`,
    fileName: fileName(article.project.title, fmt),
  });
});

router.post('/articles/:id(\\d+)/send', small, async (req, res) => {
  const ready = readyFile(req, res);
  if (!ready) return;
  const { article, fmt, file } = ready;
  try {
    await tgSendFile(req.user.id, readFileSync(file), fileName(article.project.title, fmt), `📝 ${escapeHtml(article.project.title)}`);
    res.json({ ok: true });
  } catch (error) {
    res.status(502).json({ error: telegramReason(error) });
  }
});

/** «Yangi nusxa»: joriy versiya va rasmlar alohida hujjatga ko'chiriladi. */
router.post('/articles/:id(\\d+)/copy', (req, res) => {
  const article = ownArticle(req);
  if (!article) return res.status(404).json({ error: 'Maqola topilmadi.' });
  const copyId = Number(run(
    "INSERT INTO documents (user_id, kind, title, file_id, created_at) VALUES (?, 'maqola', ?, ?, ?)",
    req.user.id, article.project.title, article.doc.file_id, nowStr(),
  ).lastInsertRowid);
  mkdirSync(mediaDir(copyId), { recursive: true });
  if (existsSync(mediaDir(article.id))) cpSync(mediaDir(article.id), mediaDir(copyId), { recursive: true });
  const now = nowStr();
  const copy = { ...article.project, rev: 1, created_at: now, updated_at: now };
  writeJson(projectFile(copyId), copy);
  writeJson(path.join(articleDir(copyId), 'original.json'), { title: copy.title, blocks: copy.blocks });
  res.status(201).json({ id: copyId });
});

// ===== Imzolangan havolalar (Authorization'siz): rasmlar va tayyor fayl =====
export const articlePublicRouter = Router();

articlePublicRouter.get('/article-media/:token/:name', (req, res) => {
  const parts = readToken(req.params.token);
  const { name } = req.params;
  if (!parts || parts[0] !== 'amedia' || !SAFE_NAME.test(name)) return res.status(403).end();
  const file = path.join(mediaDir(Number(parts[1])), name);
  if (!existsSync(file)) return res.status(404).end();
  res.sendFile(file, { maxAge: '1h', headers: { 'X-Content-Type-Options': 'nosniff' } });
});

articlePublicRouter.get('/article-file/:token', (req, res) => {
  const parts = readToken(req.params.token);
  if (!parts || parts[0] !== 'afile') return res.status(403).send("Havola eskirgan. Ilovada qaytadan «Yuklab olish» ni bosing.");
  const [, id, userId, fmt] = parts;
  const project = readJson(projectFile(Number(id)));
  const file = path.join(articleDir(Number(id)), `file.${fmt}`);
  if (!project || project.user_id !== Number(userId) || !MIME[fmt] || !existsSync(file)) return res.status(404).send('Fayl topilmadi.');
  const name = fileName(project.title, fmt);
  res.setHeader('Content-Type', MIME[fmt]);
  res.setHeader('Content-Disposition', `attachment; filename="${name.replace(/[^\w.-]/g, '_')}"; filename*=UTF-8''${encodeURIComponent(name)}`);
  res.setHeader('Cache-Control', 'no-store');
  res.send(readFileSync(file));
});

export default router;
