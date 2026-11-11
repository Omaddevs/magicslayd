import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import express, { Router } from 'express';

import { PAPERS_DIR } from '../config.js';
import { nowStr, one, run } from '../db.js';
import { makeToken, readToken } from '../signed.js';

// Referat / mustaqil ish / kurs ishi muharriri. Loyiha bot yozganda diskka saqlanadi
// (prezentatsiya_bot/documents/storage.py), bu yerda tahrirlanadi, so'ng bot faylni AI'siz qayta yasaydi
// (web_orders, kind = 'edit' — taqdimot bilan bir xil navbat: bot hujjat turini o'zi aniqlaydi)

const MEDIA_TTL = 6 * 60 * 60;
const SAFE_NAME = /^[\w.-]{1,80}$/;
const PAPER_KINDS = ['referat', 'mustaqil', 'kurs'];
const TITLE_FIELDS = ['university', 'faculty', 'subject', 'student', 'group', 'teacher', 'city'];
// Kurs ishida boblar rim raqamida (bot: documents/builder.py → ROMAN, 6 tagacha)
const LIMITS = {
  chapters: 6, sections: 8, paragraphs: 60, intro: 30, conclusion: 30, references: 40,
  paragraph: 4000, reference: 500, title: 300, heading: 200, titleField: 150,
};
const IMAGE_MAX = 10 * 1024 * 1024;

const paperDir = (id) => path.join(PAPERS_DIR, String(id));
const mediaDir = (id) => path.join(paperDir(id), 'media');
const projectFile = (id) => path.join(paperDir(id), 'paper.json');

export const isPaper = (documentId) => existsSync(projectFile(documentId));

/** Muharrirda tahrirlangan ishning eng oxirgi fayli: { file, ext } yoki null. */
export function localPaperFile(id) {
  for (const ext of ['docx', 'pdf']) {
    const file = path.join(paperDir(id), `file.${ext}`);
    if (existsSync(file)) return { file, ext };
  }
  return null;
}

class BadInput extends Error {}

function readProject(id) {
  try {
    return JSON.parse(readFileSync(projectFile(id), 'utf8'));
  } catch {
    return null;
  }
}

const ownDoc = (req) => one(
  `SELECT id, kind, title FROM documents WHERE id = ? AND user_id = ? AND kind IN (${PAPER_KINDS.map(() => '?').join(', ')})`,
  Number(req.params.id), req.user.id, ...PAPER_KINDS,
);

function ownPaper(req) {
  const doc = ownDoc(req);
  const project = doc ? readProject(doc.id) : null;
  return project && project.user_id === req.user.id ? { id: doc.id, doc, project } : null;
}

/** Shu hujjat uchun bot vazifasi (edit / import) — statuses: "'pending', 'working'" kabi. */
const job = (kind, userId, documentId, statuses) => one(
  `SELECT id FROM web_orders WHERE kind = ? AND user_id = ? AND status IN (${statuses}) AND params = ?`,
  kind, userId, JSON.stringify({ document_id: documentId }),
);

function queueJob(kind, userId, documentId) {
  return Number(run(
    'INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, ?, ?, 0, ?)',
    userId, kind, JSON.stringify({ document_id: documentId }), nowStr(),
  ).lastInsertRowid);
}

// ===== Tekshirish va tozalash =====
function str(value, max, field, { required = false } = {}) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (required && !text) throw new BadInput(`${field} bo'sh bo'lmasin.`);
  if (text.length > max) throw new BadInput(`${field} ${max} belgidan oshmasin.`);
  return text;
}

/** Xatboshilar ro'yxati: bo'shlari tashlanadi, kamida min tasi qolishi kerak. */
function texts(value, { min, max, each, field }) {
  const list = (Array.isArray(value) ? value : [])
    .map((text, i) => str(text, each, `${field}, ${i + 1}-xatboshi`)).filter(Boolean);
  if (list.length < min) throw new BadInput(`${field}: kamida ${min} ta xatboshi bo'lsin.`);
  if (list.length > max) throw new BadInput(`${field}: ${max} tadan ko'p xatboshi bo'lmasin.`);
  return list;
}

function imageName(value, id) {
  if (value == null || value === '') return null;
  const name = String(value);
  if (!SAFE_NAME.test(name) || !existsSync(path.join(mediaDir(id), name))) throw new BadInput('Rasm topilmadi, qayta yuklang.');
  return name;
}

function cleanContent(raw, id) {
  if (!raw || !Array.isArray(raw.chapters)) throw new BadInput("Hujjat ma'lumoti buzilgan.");
  if (!raw.chapters.length || raw.chapters.length > LIMITS.chapters) {
    throw new BadInput(`Boblar soni 1–${LIMITS.chapters} ta bo'lsin.`);
  }
  const chapters = raw.chapters.map((chapter, c) => {
    const sections = Array.isArray(chapter?.sections) ? chapter.sections : [];
    if (!sections.length || sections.length > LIMITS.sections) {
      throw new BadInput(`${c + 1}-bobda 1–${LIMITS.sections} ta bo'lim bo'lsin.`);
    }
    return {
      title: str(chapter.title, LIMITS.heading, `${c + 1}-bob nomi`, { required: true }),
      image: imageName(chapter.image, id),
      sections: sections.map((section, s) => ({
        title: str(section?.title, LIMITS.heading, `${c + 1}.${s + 1}-bo'lim nomi`, { required: true }),
        paragraphs: texts(section?.paragraphs, {
          min: 1, max: LIMITS.paragraphs, each: LIMITS.paragraph, field: `${c + 1}.${s + 1}-bo'lim`,
        }),
        // Bo'lim rasmi (bot: documents/ai.py) — birinchi bo'limda bob rasmi ishlatiladi
        image: s === 0 ? null : imageName(section?.image, id),
      })),
    };
  });
  return {
    title: str(raw.title, LIMITS.title, 'Ish mavzusi', { required: true }),
    intro: texts(raw.intro, { min: 1, max: LIMITS.intro, each: LIMITS.paragraph, field: 'Kirish' }),
    chapters,
    conclusion: texts(raw.conclusion, { min: 1, max: LIMITS.conclusion, each: LIMITS.paragraph, field: 'Xulosa' }),
    references: (Array.isArray(raw.references) ? raw.references : [])
      .map((ref, i) => str(ref, LIMITS.reference, `${i + 1}-adabiyot`)).filter(Boolean).slice(0, LIMITS.references),
  };
}

function cleanTitlePage(raw) {
  const page = {};
  for (const key of TITLE_FIELDS) {
    const value = str(raw?.[key], LIMITS.titleField, 'Titul maydoni');
    if (value) page[key] = value;
  }
  return page;
}

// ===== Routelar (Authorization bilan) =====
const router = Router();

router.get('/papers/:id(\\d+)', (req, res) => {
  const paper = ownPaper(req);
  if (!paper) {
    const doc = ownDoc(req);
    if (!doc) return res.status(404).json({ error: 'Hujjat topilmadi.' });
    // Loyihasi yo'q (eski ish) — bot uni fayldan tiklaydi: POST /papers/:id/import
    return res.status(404).json({
      error: 'Hujjat hali tahrirlashga tayyorlanmagan.',
      importable: true,
      pendingImport: job('import', req.user.id, doc.id, "'pending', 'working'")?.id ?? null,
    });
  }
  const { project } = paper;
  res.json({
    id: paper.id,
    kind: project.kind,
    lang: project.lang,
    fmt: project.fmt ?? 'docx',
    imported: Boolean(project.imported),
    titlePage: project.title_page ?? {},
    content: project.content,
    mediaToken: makeToken(['pmedia', paper.id, req.user.id], MEDIA_TTL),
    pendingOrder: job('edit', req.user.id, paper.id, "'pending', 'working'")?.id ?? null,
    limits: { ...LIMITS, imageMax: IMAGE_MAX },
  });
});

// Saqlash: loyiha yoziladi va bot qayta yig'ish uchun navbatga qo'yiladi
router.put('/papers/:id(\\d+)', express.json({ limit: '2mb' }), (req, res) => {
  const paper = ownPaper(req);
  if (!paper) return res.status(404).json({ error: 'Hujjat topilmadi.' });
  let content;
  let titlePage;
  try {
    content = cleanContent(req.body?.content, paper.id);
    titlePage = cleanTitlePage(req.body?.titlePage);
  } catch (error) {
    if (error instanceof BadInput) return res.status(400).json({ error: error.message });
    throw error;
  }

  const project = { ...paper.project, title_page: titlePage, content };
  // Avval vaqtinchalik faylga — yozish yarim qolsa ham loyiha buzilmaydi
  const temp = `${projectFile(paper.id)}.${process.pid}.tmp`;
  writeFileSync(temp, JSON.stringify(project));
  renameSync(temp, projectFile(paper.id));
  run('UPDATE documents SET title = ? WHERE id = ?', content.title, paper.id);

  // Endi ishlatilmayotgan rasmlar o'chiriladi
  const used = new Set(content.chapters.flatMap((chapter) => [chapter.image, ...chapter.sections.map((s) => s.image)]).filter(Boolean));
  if (existsSync(mediaDir(paper.id))) {
    for (const name of readdirSync(mediaDir(paper.id))) {
      if (used.has(name)) continue;
      try {
        unlinkSync(path.join(mediaDir(paper.id), name));
      } catch {
        // band bo'lsa — keyingi saqlashda o'chadi
      }
    }
  }

  // Navbatda turgan bo'lsa — yangisi kerak emas: bot baribir eng oxirgi paper.json ni yig'adi
  const pending = job('edit', req.user.id, paper.id, "'pending'");
  res.json({ orderId: pending?.id ?? queueJob('edit', req.user.id, paper.id) });
});

// Eski ish (loyihasi saqlanmagan) — bot DOCX/PDF fayldan loyihani tiklaydi
router.post('/papers/:id(\\d+)/import', (req, res) => {
  const doc = ownDoc(req);
  if (!doc) return res.status(404).json({ error: 'Hujjat topilmadi.' });
  if (isPaper(doc.id)) return res.json({ orderId: null, ready: true });
  res.json({ orderId: job('import', req.user.id, doc.id, "'pending', 'working'")?.id ?? queueJob('import', req.user.id, doc.id) });
});

// Bob rasmi yuklash (xom fayl). Turi ichidan tekshiriladi — Word faqat JPG/PNG ni ishonchli ko'rsatadi
router.post('/papers/:id(\\d+)/media', express.raw({ type: () => true, limit: IMAGE_MAX }), (req, res) => {
  const paper = ownPaper(req);
  if (!paper) return res.status(404).json({ error: 'Hujjat topilmadi.' });
  const data = req.body;
  if (!Buffer.isBuffer(data) || !data.length) return res.status(400).json({ error: "Fayl bo'sh." });

  let ext = null;
  if (data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) ext = 'jpg';
  else if (data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) ext = 'png';
  if (!ext) return res.status(415).json({ error: 'Faqat JPG yoki PNG rasm yuklash mumkin.' });

  mkdirSync(mediaDir(paper.id), { recursive: true });
  const name = `img-${randomUUID().slice(0, 12)}.${ext}`;
  writeFileSync(path.join(mediaDir(paper.id), name), data);
  res.status(201).json({ name, kind: 'image' });
});

// ===== Rasmlarni ko'rsatish (imzolangan havola, <img> uchun) =====
export const paperMediaRouter = Router();

paperMediaRouter.get('/paper-media/:token/:name', (req, res) => {
  const parts = readToken(req.params.token);
  const { name } = req.params;
  if (!parts || parts[0] !== 'pmedia' || !SAFE_NAME.test(name)) return res.status(403).end();
  const file = path.join(mediaDir(Number(parts[1])), name);
  if (!existsSync(file)) return res.status(404).end();
  res.sendFile(file, { maxAge: '1h', headers: { 'X-Content-Type-Options': 'nosniff' } });
});

export default router;
