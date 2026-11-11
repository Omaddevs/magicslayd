import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import express, { Router } from 'express';

import { hasPerm } from '../admins.js';
import { DIPLOMAS_DIR } from '../config.js';
import { all, db, nowStr, one, run } from '../db.js';
import { getSettings, money } from '../settings.js';
import { makeToken, readToken } from '../signed.js';

// Diplom ishi (bot: prezentatsiya_bot/diploma/). Loyiha — diplomas jadvalida bitta JSON. Bu yerda: ma'lumotlar,
// reja va matnni tahrirlash, fayl yuklash. AI ishlari (reja, tasdiqlash + to'lov, yozish, eksport) — bot navbatiga
// (web_orders, kind = 'diplom'): pul faqat bot tomonida, bir marta yechiladi.

const MEDIA_TTL = 6 * 60 * 60;
const SAFE_NAME = /^[\w.-]{1,80}$/;
const UPLOAD_MAX = 20 * 1024 * 1024;
const INFO = { topic: 300, student: 200, university: 200, faculty: 200, direction: 200, specialty: 200,
  course_group: 100, supervisor: 200, extra: 1000 };
const LANGS = ['uz', 'ru', 'en'];
const LIMITS = { chapters: 7, sections: 8, paragraphs: 40, paragraph: 6000, heading: 300, sources: 80 };
const ACTIONS = ['analyze', 'plan', 'approve_plan', 'generate', 'write_all', 'rewrite', 'sources', 'export', 'design'];
const OPS = ['expand', 'shorten', 'fix', 'style', 'regenerate'];

// Bot diploma/storage.py → EMPTY bilan bir xil tuzilma
function emptyProject(info) {
  return {
    version: 1,
    stage: 'info',
    info: { topic: '', student: '', university: '', faculty: '', direction: '', specialty: '', course_group: '',
      supervisor: '', lang: 'uz', pages: 60, extra: '', ...info },
    method: { file: null, name: null, status: 'none', rules: {}, found: [], notes: '' },
    materials: [],
    plan: { field: '', chapters: [], approved: false, sample: true },
    intro: { items: [], status: 'empty' },
    chapters: [],
    conclusion: { paragraphs: [], status: 'empty' },
    sources: [],
    ops: { date: '', count: 0, plans: 0 },
    export: { document_id: null, at: null },
  };
}

class BadInput extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

const folder = (id) => path.join(DIPLOMAS_DIR, String(id));
const str = (value, max, field, { required = false } = {}) => {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (required && !text) throw new BadInput(`${field} bo'sh bo'lmasin.`);
  if (text.length > max) throw new BadInput(`${field} ${max} belgidan oshmasin.`);
  return text;
};
const paragraphs = (value, field) => {
  const list = (Array.isArray(value) ? value : []).map((p, i) => str(p, LIMITS.paragraph, `${field}, ${i + 1}-xatboshi`)).filter(Boolean);
  if (list.length > LIMITS.paragraphs) throw new BadInput(`${field}: ${LIMITS.paragraphs} tadan ko'p xatboshi bo'lmasin.`);
  return list;
};

function load(req) {
  const row = one('SELECT * FROM diplomas WHERE id = ? AND user_id = ?', Number(req.params.id), req.user.id);
  if (!row) return null;
  return { row, project: { ...emptyProject(), ...JSON.parse(row.data) } };
}

/** Atomar o'zgartirish (bot bilan bir xil: o'qi → o'zgartir → yoz — bitta tranzaksiyada). */
function update(id, change) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const row = one('SELECT data FROM diplomas WHERE id = ?', id);
    if (!row) throw new BadInput('Diplom ishi topilmadi.', 404);
    const project = { ...emptyProject(), ...JSON.parse(row.data) };
    const result = change(project);
    run('UPDATE diplomas SET data = ?, title = ?, updated_at = ? WHERE id = ?', JSON.stringify(project), project.info.topic, nowStr(), id);
    db.exec('COMMIT');
    return [project, result];
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}

const priceFor = (userId, pages, settings = getSettings()) =>
  hasPerm(userId, 'free') ? 0 : Number(pages) * (settings.diploma?.page_price ?? 700);

function activeJobs(userId, id) {
  return all(
    "SELECT id, params, status FROM web_orders WHERE kind = 'diplom' AND user_id = ? AND status IN ('pending', 'working') " +
      "AND json_extract(params, '$.diploma_id') = ? ORDER BY id",
    userId, id,
  ).map((job) => ({ id: job.id, status: job.status, ...JSON.parse(job.params) }));
}

function view(req, row, project) {
  const settings = getSettings();
  return {
    id: row.id,
    paid: Boolean(row.paid),
    documentId: row.document_id,
    price: priceFor(req.user.id, project.info.pages, settings),
    balance: one('SELECT balance FROM users WHERE id = ?', req.user.id)?.balance ?? 0,
    project,
    jobs: activeJobs(req.user.id, row.id),
    mediaToken: makeToken(['dmedia', row.id, req.user.id], MEDIA_TTL),
    pdf: Boolean(settings.pdf),
  };
}

const handle = (fn) => (req, res, next) => {
  try {
    fn(req, res, next);
  } catch (error) {
    if (error instanceof BadInput) return res.status(error.status).json({ error: error.message });
    next(error);
  }
};

// ===== Routelar (Authorization bilan) =====
const router = Router();

router.get('/diplomas', (req, res) => {
  const rows = all('SELECT id, title, paid, data, updated_at FROM diplomas WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 20', req.user.id);
  res.json({
    diplomas: rows.map((row) => {
      const project = JSON.parse(row.data);
      return { id: row.id, title: row.title, paid: Boolean(row.paid), stage: project.stage, pages: project.info?.pages, updated_at: row.updated_at };
    }),
  });
});

router.get('/diplomas/by-document/:doc(\\d+)', (req, res) => {
  const row = one('SELECT id FROM diplomas WHERE document_id = ? AND user_id = ?', Number(req.params.doc), req.user.id);
  if (!row) return res.status(404).json({ error: 'Diplom ishi topilmadi.' });
  res.json({ id: row.id });
});

router.post('/diplomas', handle((req, res) => {
  const info = { topic: str(req.body?.topic, INFO.topic, 'Mavzu', { required: true }) };
  if (info.topic.length < 5) throw new BadInput('Mavzu kamida 5 belgi bo\'lsin.');
  const project = emptyProject(info);
  const id = Number(run(
    'INSERT INTO diplomas (user_id, title, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
    req.user.id, info.topic, JSON.stringify(project), nowStr(), nowStr(),
  ).lastInsertRowid);
  res.status(201).json({ id });
}));

router.get('/diplomas/:id(\\d+)', (req, res) => {
  const loaded = load(req);
  if (!loaded) return res.status(404).json({ error: 'Diplom ishi topilmadi.' });
  res.json(view(req, loaded.row, loaded.project));
});

router.delete('/diplomas/:id(\\d+)', (req, res) => {
  const loaded = load(req);
  if (!loaded) return res.status(404).json({ error: 'Diplom ishi topilmadi.' });
  if (loaded.row.paid) return res.status(400).json({ error: "To'langan ishni o'chirib bo'lmaydi." });
  run('DELETE FROM diplomas WHERE id = ?', loaded.row.id);
  res.json({ ok: true });
});

router.put('/diplomas/:id(\\d+)/info', express.json({ limit: '50kb' }), handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const settings = getSettings();
  const body = req.body ?? {};
  const values = {};
  for (const [key, max] of Object.entries(INFO)) {
    if (key in body) values[key] = str(body[key], max, 'Maydon', { required: key === 'topic' });
  }
  const locked = loaded.project.plan.approved;
  if ('lang' in body) {
    if (!LANGS.includes(body.lang)) throw new BadInput('Tilni tanlang.');
    if (locked && body.lang !== loaded.project.info.lang) throw new BadInput("Reja tasdiqlangan — tilni o'zgartirib bo'lmaydi.");
    values.lang = body.lang;
  }
  if ('pages' in body) {
    const pages = Number(body.pages);
    const { min = 40, max = 150 } = settings.diploma ?? {};
    if (!Number.isInteger(pages) || pages < min || pages > max) throw new BadInput(`Hajm ${min}–${max} bet oralig'ida bo'lsin.`);
    if (locked && pages !== loaded.project.info.pages) throw new BadInput("Reja tasdiqlangan — hajmni o'zgartirib bo'lmaydi.");
    values.pages = pages;
  }
  const [project] = update(loaded.row.id, (p) => Object.assign(p.info, values));
  res.json(view(req, loaded.row, project));
}));

router.put('/diplomas/:id(\\d+)/plan', express.json({ limit: '200kb' }), handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const raw = Array.isArray(req.body?.chapters) ? req.body.chapters : [];
  if (raw.length < 1 || raw.length > LIMITS.chapters) throw new BadInput(`Boblar soni 1–${LIMITS.chapters} ta bo'lsin.`);
  const chapters = raw.map((c, i) => {
    const sections = (Array.isArray(c?.sections) ? c.sections : []).map((s, j) => ({
      title: str(s?.title, LIMITS.heading, `${i + 1}.${j + 1}-paragraf nomi`, { required: true }),
    }));
    if (!sections.length || sections.length > LIMITS.sections) throw new BadInput(`${i + 1}-bobda 1–${LIMITS.sections} ta paragraf bo'lsin.`);
    return { title: str(c?.title, LIMITS.heading, `${i + 1}-bob nomi`, { required: true }), sections };
  });
  const [project] = update(loaded.row.id, (p) => {
    if (p.plan.approved) throw new BadInput("Reja tasdiqlangan — endi o'zgartirib bo'lmaydi.");
    p.plan.chapters = chapters;
  });
  res.json(view(req, loaded.row, project));
}));

/** Qism matnini saqlash (foydalanuvchi tahriri). Tuzilma (bo'limlar soni) o'zgarmaydi, xatboshilar — erkin. */
router.put('/diplomas/:id(\\d+)/part', express.json({ limit: '2mb' }), handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const key = String(req.body?.part ?? '');
  const data = req.body?.data ?? {};
  const [project] = update(loaded.row.id, (p) => {
    if (key === 'intro') {
      const items = Array.isArray(data.items) ? data.items : [];
      if (items.length !== p.intro.items.length) throw new BadInput("Kirish tuzilmasi o'zgarmasin.");
      p.intro.items = p.intro.items.map((item, i) => ({ label: item.label, paragraphs: paragraphs(items[i]?.paragraphs, item.label) }));
    } else if (key === 'conclusion') {
      p.conclusion.paragraphs = paragraphs(data.paragraphs, 'Xulosa');
    } else if (/^chapter:\d+$/.test(key) && Number(key.slice(8)) < p.chapters.length) {
      const chapter = p.chapters[Number(key.slice(8))];
      const sections = Array.isArray(data.sections) ? data.sections : [];
      if (sections.length !== chapter.sections.length) throw new BadInput("Bob tuzilmasi o'zgarmasin.");
      chapter.sections = chapter.sections.map((s, i) => ({
        title: str(sections[i]?.title ?? s.title, LIMITS.heading, 'Paragraf nomi', { required: true }),
        paragraphs: paragraphs(sections[i]?.paragraphs, `${i + 1}-paragraf`),
      }));
      chapter.summary = paragraphs(data.summary, 'Bob xulosasi');
      if (Array.isArray(data.figures)) {
        // Faqat mavjud rasmlar: nomini o'zgartirish yoki o'chirish (yangi rasm — /upload orqali)
        const keep = new Map(data.figures.map((f) => [f?.id, f]));
        chapter.figures = (chapter.figures ?? []).filter((f) => keep.has(f.id)).map((f) => ({
          ...f,
          caption: str(keep.get(f.id).caption ?? f.caption, LIMITS.heading, 'Rasm nomi', { required: true }),
          file: f.kind !== 'table' && keep.get(f.id).file && SAFE_NAME.test(keep.get(f.id).file) &&
            existsSync(path.join(folder(loaded.row.id), keep.get(f.id).file)) ? keep.get(f.id).file : f.file,
          source: keep.get(f.id).file && keep.get(f.id).file !== f.file ? 'Muallif tomonidan yuklangan' : f.source,
        }));
      }
    } else {
      throw new BadInput('Bunday qism yo\'q.');
    }
  });
  res.json(view(req, loaded.row, project));
}));

router.post('/diplomas/:id(\\d+)/approve-part', express.json({ limit: '5kb' }), handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const key = String(req.body?.part ?? '');
  const [project] = update(loaded.row.id, (p) => {
    const part = key === 'intro' ? p.intro : key === 'conclusion' ? p.conclusion
      : /^chapter:\d+$/.test(key) ? p.chapters[Number(key.slice(8))] : null;
    if (!part) throw new BadInput('Bunday qism yo\'q.');
    const hasText = key === 'intro' ? part.items.length : key === 'conclusion' ? part.paragraphs.length
      : part.sections.some((s) => s.paragraphs.length);
    if (!hasText) throw new BadInput('Bu qism hali yozilmagan.');
    part.status = req.body?.approved === false ? 'draft' : 'approved';
    const parts = [p.intro, ...p.chapters, p.conclusion];
    p.stage = parts.every((x) => x.status === 'approved') ? 'done' : 'writing';
  });
  res.json(view(req, loaded.row, project));
}));

router.put('/diplomas/:id(\\d+)/sources', express.json({ limit: '200kb' }), handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const keep = new Set((Array.isArray(req.body?.keep) ? req.body.keep : []).map(Number));
  const added = (Array.isArray(req.body?.add) ? req.body.add : []).slice(0, 10).map((s) => {
    const year = Number(s?.year);
    if (!Number.isInteger(year) || year < 1800 || year > new Date().getFullYear() + 1) throw new BadInput("Manba yilini to'g'ri yozing.");
    return {
      authors: str(s?.authors, 300, 'Muallif', { required: true }), title: str(s?.title, 400, 'Manba nomi', { required: true }),
      year, venue: str(s?.venue, 300, 'Nashr'), doi: '', url: str(s?.url, 500, 'Havola'),
      verified: false, origin: 'Foydalanuvchi', cited: 0,
    };
  });
  const [project] = update(loaded.row.id, (p) => {
    let n = Math.max(0, ...p.sources.map((s) => s.n));
    p.sources = [...p.sources.filter((s) => keep.has(s.n)), ...added.map((s) => ({ ...s, n: ++n }))];
    if (p.sources.length > LIMITS.sources) throw new BadInput(`Manbalar ${LIMITS.sources} tadan oshmasin.`);
  });
  res.json(view(req, loaded.row, project));
}));

// Fayl yuklash: purpose = method (qo'llanma) | material (amaliy qism) | figure (rasm almashtirish)
router.post('/diplomas/:id(\\d+)/upload', express.raw({ type: () => true, limit: UPLOAD_MAX }), handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const purpose = String(req.query.purpose ?? '');
  const data = req.body;
  if (!Buffer.isBuffer(data) || !data.length) throw new BadInput("Fayl bo'sh.");
  let name = 'fayl';
  try {
    name = decodeURIComponent(req.get('X-File-Name') || '').replace(/[\\/]/g, '').slice(0, 120) || name;
  } catch {
    // noto'g'ri kodlangan nom
  }
  let ext = null;
  if (data.subarray(0, 4).toString('latin1') === '%PDF') ext = 'pdf';
  else if (data.subarray(0, 2).toString('latin1') === 'PK') {
    const tail = data.subarray(Math.max(0, data.length - 65536)).toString('latin1');
    ext = tail.includes('word/') ? 'docx' : tail.includes('xl/') ? 'xlsx' : null;
  } else if (data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) ext = 'jpg';
  else if (data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) ext = 'png';
  else if (/\.(csv|txt)$/i.test(name) && !data.subarray(0, 4000).includes(0)) ext = name.toLowerCase().endsWith('.csv') ? 'csv' : 'txt';
  const allowed = { method: ['pdf', 'docx', 'txt'], material: ['pdf', 'docx', 'xlsx', 'csv', 'txt'], figure: ['jpg', 'png'] }[purpose];
  if (!allowed) throw new BadInput("Noma'lum yuklash.");
  if (!ext || !allowed.includes(ext)) {
    throw new BadInput(purpose === 'figure' ? 'Faqat JPG yoki PNG rasm.' : `Faqat ${allowed.map((x) => x.toUpperCase()).join(', ')} fayl.`, 415);
  }
  mkdirSync(folder(loaded.row.id), { recursive: true });
  const file = `${purpose === 'figure' ? 'fig' : purpose}-${randomUUID().slice(0, 10)}.${ext}`;
  writeFileSync(path.join(folder(loaded.row.id), file), data);
  if (purpose === 'figure') return res.status(201).json({ file });
  const [project] = update(loaded.row.id, (p) => {
    if (purpose === 'method') {
      if (p.plan.approved) throw new BadInput('Reja tasdiqlangan — qo\'llanmani endi almashtirib bo\'lmaydi.');
      p.method = { file, name, status: 'uploaded', rules: {}, found: [], notes: '' };
    } else {
      p.materials = [...(p.materials ?? []).slice(-9), { file, name, chars: data.length }];
    }
  });
  res.status(201).json(view(req, loaded.row, project));
}));

router.delete('/diplomas/:id(\\d+)/material/:file', handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const { file } = req.params;
  const [project] = update(loaded.row.id, (p) => {
    p.materials = (p.materials ?? []).filter((m) => m.file !== file);
  });
  if (SAFE_NAME.test(file) && existsSync(path.join(folder(loaded.row.id), file))) {
    try {
      unlinkSync(path.join(folder(loaded.row.id), file));
    } catch {
      // band bo'lsa — keyin
    }
  }
  res.json(view(req, loaded.row, project));
}));

// AI vazifasi → bot navbati. Bir diplomda bir vaqtda bitta vazifa
router.post('/diplomas/:id(\\d+)/jobs', express.json({ limit: '10kb' }), handle((req, res) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Diplom ishi topilmadi.', 404);
  const { row, project } = loaded;
  const action = req.body?.action;
  if (!ACTIONS.includes(action)) throw new BadInput("Noma'lum amal.");
  const busy = activeJobs(req.user.id, row.id);
  if (busy.length) return res.status(409).json({ error: 'Oldingi amal hali bajarilmoqda, biroz kuting.', orderId: busy[0].id });
  const params = { diploma_id: row.id, action };
  if (action === 'generate' || action === 'rewrite') {
    params.part = String(req.body?.part ?? '');
    if (!/^(intro|conclusion|chapter:\d+)$/.test(params.part)) throw new BadInput('Qismni tanlang.');
  }
  if (action === 'rewrite') {
    if (!OPS.includes(req.body?.op)) throw new BadInput("Noma'lum amal.");
    params.op = req.body.op;
    const a = req.body?.address ?? {};
    params.address = Object.fromEntries(['item', 'section', 'paragraph'].filter((k) => Number.isInteger(a[k])).map((k) => [k, a[k]]));
    if (a.summary === true) params.address.summary = true;
  }
  if (action === 'export' || action === 'design') params.fmt = req.body?.fmt === 'pdf' ? 'pdf' : 'docx';
  if (action === 'design') {
    // Rasmiylashtirish dizayni (bot diploma/designs.py tekshiradi) — matn o'zgarmaydi, pul yechilmaydi
    const design = String(req.body?.design ?? '');
    if (!/^[a-z]{2,20}$/.test(design)) throw new BadInput("Noma'lum dizayn.");
    params.design = design;
  }
  if (action === 'approve_plan' && !row.paid) {
    const price = priceFor(req.user.id, project.info.pages);
    const balance = one('SELECT balance FROM users WHERE id = ?', req.user.id)?.balance ?? 0;
    if (balance < price) {
      return res.status(402).json({ error: `Balans yetarli emas — yana ${money(price - balance)} kerak.`, need: price - balance });
    }
  }
  const orderId = Number(run(
    "INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, 'diplom', ?, 0, ?)",
    req.user.id, JSON.stringify(params), nowStr(),
  ).lastInsertRowid);
  res.status(201).json({ orderId });
}));

// ===== Rasmlar (imzolangan havola, <img> uchun) =====
export const diplomaMediaRouter = Router();

diplomaMediaRouter.get('/diploma-media/:token/:name', (req, res) => {
  const parts = readToken(req.params.token);
  const { name } = req.params;
  if (!parts || parts[0] !== 'dmedia' || !SAFE_NAME.test(name) || !/\.(png|jpg)$/i.test(name)) return res.status(403).end();
  const file = path.join(folder(Number(parts[1])), name);
  if (!existsSync(file)) return res.status(404).end();
  res.sendFile(file, { maxAge: '1h', headers: { 'X-Content-Type-Options': 'nosniff' } });
});

export default router;
