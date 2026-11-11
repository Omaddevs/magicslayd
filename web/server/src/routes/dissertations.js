import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import express, { Router } from 'express';

import { hasPerm } from '../admins.js';
import { DISS_DIR } from '../config.js';
import { all, db, nowStr, one, run } from '../db.js';
import { getSettings, money } from '../settings.js';
import { makeToken, readToken } from '../signed.js';

// Dissertatsiya (bot: prezentatsiya_bot/dissertation/). Loyiha — dissertations jadvalida bitta JSON.
// Bu yerda: ma'lumotlar, reja va matn tahriri, fayl yuklash, rasm/jadval qo'shish, oldingi versiyaga qaytish.
// AI ishlari (mavzu, reja, tasdiqlash + to'lov, yozish, tekshirish, eksport) — bot navbatiga (web_orders, kind = 'diss').

const MEDIA_TTL = 6 * 60 * 60;
const SAFE_NAME = /^[\w.-]{1,80}$/;
const UPLOAD_MAX = 20 * 1024 * 1024;
const KINDS = ['master', 'phd', 'dsc', 'other'];
const INFO = { student: 200, university: 250, faculty: 250, specialty: 200, specialty_code: 40, degree: 250, supervisor: 250,
  topic: 300, direction: 200, problem: 600, existing: 1500, extra: 1000 };
const LANGS = ['uz', 'ru', 'en'];
const LIMITS = { chapters: 7, sections: 8, paragraphs: 60, paragraph: 6000, heading: 300, sources: 120, history: 5 };
const ACTIONS = ['topics', 'analyze', 'plan', 'approve_plan', 'generate', 'write_all', 'rewrite', 'sources', 'quality', 'export', 'design'];
const OPS = ['expand', 'shorten', 'fix', 'style', 'regenerate'];
const PART = /^(intro|conclusion|annotation|chapter:\d+)$/;

// Bot dissertation/storage.py → EMPTY bilan bir xil
function emptyProject(kind = '', info = {}) {
  return {
    version: 1, stage: kind ? 'info' : 'type', kind,
    info: { student: '', university: '', faculty: '', specialty: '', specialty_code: '', degree: '', supervisor: '',
      lang: 'uz', pages: 80, topic: '', direction: '', problem: '', existing: '', extra: '', ...info },
    suggestions: [],
    method: { file: null, name: null, status: 'none', rules: {}, found: [], notes: '' },
    materials: [],
    plan: { field: '', chapters: [], approved: false, sample: true, queries: [] },
    intro: { items: [], status: 'empty' },
    chapters: [],
    conclusion: { paragraphs: [], status: 'empty' },
    annotation: { paragraphs: [], keywords: [], status: 'empty' },
    sources: [],
    history: {},
    quality: { at: null, checks: [], review: [] },
    ops: { date: '', count: 0, plans: 0 },
  };
}

function merge(data) {
  const base = emptyProject();
  const project = { ...base, ...JSON.parse(data) };
  for (const key of ['info', 'method', 'plan', 'intro', 'conclusion', 'annotation', 'quality', 'ops']) {
    project[key] = { ...base[key], ...(project[key] ?? {}) };
  }
  return project;
}

class BadInput extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

const folder = (id) => path.join(DISS_DIR, String(id));
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
const partOf = (p, key) => (['intro', 'conclusion', 'annotation'].includes(key) ? p[key]
  : /^chapter:\d+$/.test(key) ? p.chapters[Number(key.slice(8))] : null);
const hasText = (p, key) => {
  const part = partOf(p, key);
  if (!part) return false;
  if (key === 'intro') return part.items.length > 0;
  if (key === 'conclusion' || key === 'annotation') return part.paragraphs.length > 0;
  return part.sections.some((s) => s.paragraphs.length);
};
const partKeys = (p) => ['intro', ...p.chapters.map((_, i) => `chapter:${i}`), 'conclusion', 'annotation'];

function load(req) {
  const row = one('SELECT * FROM dissertations WHERE id = ? AND user_id = ?', Number(req.params.id), req.user.id);
  return row ? { row, project: merge(row.data) } : null;
}

function update(id, change) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const row = one('SELECT data FROM dissertations WHERE id = ?', id);
    if (!row) throw new BadInput('Dissertatsiya topilmadi.', 404);
    const project = merge(row.data);
    change(project);
    run('UPDATE dissertations SET data = ?, title = ?, updated_at = ? WHERE id = ?', JSON.stringify(project), project.info.topic, nowStr(), id);
    db.exec('COMMIT');
    return project;
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}

const priceFor = (userId, pages, settings = getSettings()) =>
  hasPerm(userId, 'free') ? 0 : Number(pages) * (settings.dissertation?.page_price ?? 800);

function activeJobs(userId, id) {
  return all(
    "SELECT id, params, status FROM web_orders WHERE kind = 'diss' AND user_id = ? AND status IN ('pending', 'working') " +
      "AND json_extract(params, '$.diss_id') = ? ORDER BY id",
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
    mediaToken: makeToken(['smedia', row.id, req.user.id], MEDIA_TTL),
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
const found = (req) => {
  const loaded = load(req);
  if (!loaded) throw new BadInput('Dissertatsiya topilmadi.', 404);
  return loaded;
};

/** Qism hozirgi holatini tarixga qo'yadi (bot storage.remember bilan bir xil). */
function remember(p, key, reason) {
  const part = partOf(p, key);
  if (!part || !hasText(p, key)) return;
  const list = p.history[key] ?? [];
  list.push({ at: nowStr(), reason, data: JSON.parse(JSON.stringify(part)) });
  p.history[key] = list.slice(-LIMITS.history);
}

// ===== Routelar (Authorization bilan) =====
const router = Router();

router.get('/dissertations', (req, res) => {
  const rows = all('SELECT id, title, paid, data, updated_at FROM dissertations WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT 20', req.user.id);
  res.json({
    items: rows.map((row) => {
      const p = merge(row.data);
      return { id: row.id, title: row.title, paid: Boolean(row.paid), stage: p.stage, kind: p.kind, pages: p.info.pages, updated_at: row.updated_at };
    }),
  });
});

router.get('/dissertations/by-document/:doc(\\d+)', (req, res) => {
  const row = one('SELECT id FROM dissertations WHERE document_id = ? AND user_id = ?', Number(req.params.doc), req.user.id);
  if (!row) return res.status(404).json({ error: 'Dissertatsiya topilmadi.' });
  res.json({ id: row.id });
});

router.post('/dissertations', express.json({ limit: '10kb' }), handle((req, res) => {
  const kind = req.body?.kind;
  if (!KINDS.includes(kind)) throw new BadInput('Dissertatsiya turini tanlang.');
  const pages = getSettings().dissertation?.types?.[kind]?.pages ?? 80;
  const project = emptyProject(kind, { pages });
  const id = Number(run(
    'INSERT INTO dissertations (user_id, title, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
    req.user.id, '', JSON.stringify(project), nowStr(), nowStr(),
  ).lastInsertRowid);
  res.status(201).json({ id });
}));

router.get('/dissertations/:id(\\d+)', handle((req, res) => {
  const { row, project } = found(req);
  res.json(view(req, row, project));
}));

router.delete('/dissertations/:id(\\d+)', handle((req, res) => {
  const { row } = found(req);
  if (row.paid) throw new BadInput("To'langan ishni o'chirib bo'lmaydi.");
  run('DELETE FROM dissertations WHERE id = ?', row.id);
  res.json({ ok: true });
}));

router.put('/dissertations/:id(\\d+)/info', express.json({ limit: '60kb' }), handle((req, res) => {
  const { row, project: current } = found(req);
  const settings = getSettings();
  const body = req.body ?? {};
  const values = {};
  for (const [key, max] of Object.entries(INFO)) if (key in body) values[key] = str(body[key], max, 'Maydon');
  const locked = current.plan.approved;
  if ('lang' in body) {
    if (!LANGS.includes(body.lang)) throw new BadInput('Tilni tanlang.');
    if (locked && body.lang !== current.info.lang) throw new BadInput("Reja tasdiqlangan — tilni o'zgartirib bo'lmaydi.");
    values.lang = body.lang;
  }
  if ('pages' in body) {
    const pages = Number(body.pages);
    const { min = 50, max = 300 } = settings.dissertation ?? {};
    if (!Number.isInteger(pages) || pages < min || pages > max) throw new BadInput(`Hajm ${min}–${max} bet oralig'ida bo'lsin.`);
    if (locked && pages !== current.info.pages) throw new BadInput("Reja tasdiqlangan — hajmni o'zgartirib bo'lmaydi.");
    values.pages = pages;
  }
  let kind;
  if ('kind' in body && body.kind !== current.kind) {
    if (!KINDS.includes(body.kind)) throw new BadInput('Dissertatsiya turini tanlang.');
    if (locked) throw new BadInput("Reja tasdiqlangan — turini o'zgartirib bo'lmaydi.");
    kind = body.kind;
  }
  const project = update(row.id, (p) => {
    Object.assign(p.info, values);
    if (kind) {
      p.kind = kind;
      if (!('pages' in body)) p.info.pages = settings.dissertation?.types?.[kind]?.pages ?? p.info.pages;
    }
  });
  res.json(view(req, row, project));
}));

router.put('/dissertations/:id(\\d+)/plan', express.json({ limit: '200kb' }), handle((req, res) => {
  const { row } = found(req);
  const raw = Array.isArray(req.body?.chapters) ? req.body.chapters : [];
  if (raw.length < 1 || raw.length > LIMITS.chapters) throw new BadInput(`Boblar soni 1–${LIMITS.chapters} ta bo'lsin.`);
  const chapters = raw.map((c, i) => {
    const sections = (Array.isArray(c?.sections) ? c.sections : []).map((s, j) => ({
      title: str(s?.title, LIMITS.heading, `${i + 1}.${j + 1}-paragraf nomi`, { required: true }),
    }));
    if (!sections.length || sections.length > LIMITS.sections) throw new BadInput(`${i + 1}-bobda 1–${LIMITS.sections} ta paragraf bo'lsin.`);
    return { title: str(c?.title, LIMITS.heading, `${i + 1}-bob nomi`, { required: true }), sections };
  });
  const project = update(row.id, (p) => {
    if (p.plan.approved) throw new BadInput("Reja tasdiqlangan — endi o'zgartirib bo'lmaydi.");
    p.plan.chapters = chapters;
  });
  res.json(view(req, row, project));
}));

/** Qism matnini saqlash (foydalanuvchi tahriri). Tuzilma o'zgarmaydi; rasm/jadval: nom, almashtirish, o'chirish. */
router.put('/dissertations/:id(\\d+)/part', express.json({ limit: '3mb' }), handle((req, res) => {
  const { row } = found(req);
  const key = String(req.body?.part ?? '');
  const data = req.body?.data ?? {};
  const project = update(row.id, (p) => {
    const part = PART.test(key) ? partOf(p, key) : null;
    if (!part) throw new BadInput("Bunday qism yo'q.");
    if (key === 'intro') {
      const items = Array.isArray(data.items) ? data.items : [];
      if (items.length !== part.items.length) throw new BadInput("Kirish tuzilmasi o'zgarmasin.");
      part.items = part.items.map((item, i) => ({ label: item.label, paragraphs: paragraphs(items[i]?.paragraphs, item.label) }));
    } else if (key === 'conclusion') {
      part.paragraphs = paragraphs(data.paragraphs, 'Xulosa');
    } else if (key === 'annotation') {
      part.paragraphs = paragraphs(data.paragraphs, 'Annotatsiya');
      part.keywords = (Array.isArray(data.keywords) ? data.keywords : []).map((k) => str(k, 60, "Kalit so'z")).filter(Boolean).slice(0, 12);
    } else {
      const sections = Array.isArray(data.sections) ? data.sections : [];
      if (sections.length !== part.sections.length) throw new BadInput("Bob tuzilmasi o'zgarmasin.");
      part.sections = part.sections.map((s, i) => ({
        title: str(sections[i]?.title ?? s.title, LIMITS.heading, 'Paragraf nomi', { required: true }),
        paragraphs: paragraphs(sections[i]?.paragraphs, `${i + 1}-paragraf`),
      }));
      part.summary = paragraphs(data.summary, 'Bob xulosasi');
      if (Array.isArray(data.figures)) {
        const incoming = new Map(data.figures.map((f) => [f?.id, f]));
        const fileOk = (name) => name && SAFE_NAME.test(name) && existsSync(path.join(folder(row.id), name));
        part.figures = part.figures.filter((f) => incoming.has(f.id)).map((f) => {
          const next = incoming.get(f.id);
          const replaced = f.kind !== 'table' && next.file !== f.file && fileOk(next.file);
          return { ...f, caption: str(next.caption ?? f.caption, LIMITS.heading, 'Rasm nomi', { required: true }),
            file: replaced ? next.file : f.file, source: replaced ? 'Muallif tomonidan yuklangan' : f.source };
        });
      }
    }
  });
  res.json(view(req, row, project));
}));

// Yangi rasm (yuklangan fayl) yoki jadval qo'shish — bobning tanlangan paragrafiga
router.post('/dissertations/:id(\\d+)/figure', express.json({ limit: '100kb' }), handle((req, res) => {
  const { row } = found(req);
  const key = String(req.body?.part ?? '');
  const kind = req.body?.kind === 'table' ? 'table' : 'image';
  const caption = str(req.body?.caption, LIMITS.heading, 'Nomi', { required: true });
  const source = str(req.body?.source, 300, 'Manba') || 'Muallif tomonidan tuzilgan';
  const project = update(row.id, (p) => {
    const chapter = /^chapter:\d+$/.test(key) ? partOf(p, key) : null;
    if (!chapter) throw new BadInput('Bobni tanlang.');
    const section = Number(req.body?.section ?? 0);
    if (!Number.isInteger(section) || section < 0 || section >= chapter.sections.length) throw new BadInput('Paragrafni tanlang.');
    const paragraph = Math.max(0, chapter.sections[section].paragraphs.length - 1);
    const item = { id: randomUUID().slice(0, 10), kind, caption, section, paragraph, source };
    if (kind === 'table') {
      const columns = (Array.isArray(req.body?.columns) ? req.body.columns : []).map((c) => str(c, 100, 'Ustun')).filter(Boolean).slice(0, 6);
      const rows = (Array.isArray(req.body?.rows) ? req.body.rows : []).slice(0, 30)
        .map((r) => columns.map((_, i) => str(Array.isArray(r) ? r[i] : '', 300, 'Katak')));
      if (columns.length < 2 || !rows.length) throw new BadInput("Jadvalda kamida 2 ustun va 1 qator bo'lsin.");
      Object.assign(item, { columns, rows });
    } else {
      const file = String(req.body?.file ?? '');
      if (!SAFE_NAME.test(file) || !existsSync(path.join(folder(row.id), file))) throw new BadInput('Rasm topilmadi, qayta yuklang.');
      item.kind = 'illustration';
      item.file = file;
    }
    remember(p, key, 'Rasm/jadval qo\'shishdan oldin');
    chapter.figures = [...(chapter.figures ?? []), item];
  });
  res.status(201).json(view(req, row, project));
}));

router.post('/dissertations/:id(\\d+)/approve-part', express.json({ limit: '5kb' }), handle((req, res) => {
  const { row } = found(req);
  const key = String(req.body?.part ?? '');
  const project = update(row.id, (p) => {
    if (!PART.test(key) || !partOf(p, key)) throw new BadInput("Bunday qism yo'q.");
    if (!hasText(p, key)) throw new BadInput('Bu qism hali yozilmagan.');
    partOf(p, key).status = req.body?.approved === false ? 'draft' : 'approved';
    p.stage = partKeys(p).every((k) => partOf(p, k).status === 'approved') ? 'done' : 'writing';
  });
  res.json(view(req, row, project));
}));

// Oldingi versiyaga qaytish: tanlangan versiya qismga qaytadi, hozirgisi esa tarixga tushadi (yana qaytarsa bo'ladi)
router.post('/dissertations/:id(\\d+)/restore', express.json({ limit: '5kb' }), handle((req, res) => {
  const { row } = found(req);
  const key = String(req.body?.part ?? '');
  const index = Number(req.body?.index);
  const project = update(row.id, (p) => {
    const list = p.history[key] ?? [];
    if (!PART.test(key) || !Number.isInteger(index) || !list[index]) throw new BadInput('Versiya topilmadi.');
    const [version] = list.splice(index, 1);
    p.history[key] = list;
    remember(p, key, 'Versiya qaytarilishidan oldin');
    const restored = { ...version.data, status: 'draft' };
    if (key.startsWith('chapter:')) p.chapters[Number(key.slice(8))] = restored;
    else p[key] = restored;
  });
  res.json(view(req, row, project));
}));

router.put('/dissertations/:id(\\d+)/sources', express.json({ limit: '200kb' }), handle((req, res) => {
  const { row } = found(req);
  const keep = new Set((Array.isArray(req.body?.keep) ? req.body.keep : []).map(Number));
  const added = (Array.isArray(req.body?.add) ? req.body.add : []).slice(0, 10).map((s) => {
    const year = Number(s?.year);
    if (!Number.isInteger(year) || year < 1800 || year > new Date().getFullYear() + 1) throw new BadInput("Manba yilini to'g'ri yozing.");
    return { authors: str(s?.authors, 300, 'Muallif', { required: true }), title: str(s?.title, 400, 'Manba nomi', { required: true }),
      year, venue: str(s?.venue, 300, 'Nashr'), doi: '', url: str(s?.url, 500, 'Havola'), verified: false, origin: 'Foydalanuvchi', cited: 0 };
  });
  const project = update(row.id, (p) => {
    let n = Math.max(0, ...p.sources.map((s) => s.n));
    p.sources = [...p.sources.filter((s) => keep.has(s.n)), ...added.map((s) => ({ ...s, n: ++n }))];
    if (p.sources.length > LIMITS.sources) throw new BadInput(`Manbalar ${LIMITS.sources} tadan oshmasin.`);
  });
  res.json(view(req, row, project));
}));

// Fayl yuklash: method (qo'llanma) | material (ma'lumot, hujjat) | figure (rasm)
router.post('/dissertations/:id(\\d+)/upload', express.raw({ type: () => true, limit: UPLOAD_MAX }), handle((req, res) => {
  const { row } = found(req);
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
  mkdirSync(folder(row.id), { recursive: true });
  const file = `${purpose === 'figure' ? 'fig' : purpose}-${randomUUID().slice(0, 10)}.${ext}`;
  writeFileSync(path.join(folder(row.id), file), data);
  if (purpose === 'figure') return res.status(201).json({ file });
  const project = update(row.id, (p) => {
    if (purpose === 'method') {
      if (p.plan.approved) throw new BadInput("Reja tasdiqlangan — qo'llanmani endi almashtirib bo'lmaydi.");
      p.method = { file, name, status: 'uploaded', rules: {}, found: [], notes: '' };
    } else {
      p.materials = [...p.materials.slice(-14), { file, name, kind: ext }];
    }
  });
  res.status(201).json(view(req, row, project));
}));

router.delete('/dissertations/:id(\\d+)/material/:file', handle((req, res) => {
  const { row } = found(req);
  const { file } = req.params;
  const project = update(row.id, (p) => {
    p.materials = p.materials.filter((m) => m.file !== file);
  });
  if (SAFE_NAME.test(file) && existsSync(path.join(folder(row.id), file))) {
    try {
      unlinkSync(path.join(folder(row.id), file));
    } catch {
      // band bo'lsa — keyin
    }
  }
  res.json(view(req, row, project));
}));

router.post('/dissertations/:id(\\d+)/jobs', express.json({ limit: '10kb' }), handle((req, res) => {
  const { row, project } = found(req);
  const action = req.body?.action;
  if (!ACTIONS.includes(action)) throw new BadInput("Noma'lum amal.");
  const busy = activeJobs(req.user.id, row.id);
  if (busy.length) return res.status(409).json({ error: 'Oldingi amal hali bajarilmoqda, biroz kuting.', orderId: busy[0].id });
  const params = { diss_id: row.id, action };
  if (action === 'generate' || action === 'rewrite') {
    params.part = String(req.body?.part ?? '');
    if (!PART.test(params.part)) throw new BadInput('Qismni tanlang.');
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
    if (balance < price) return res.status(402).json({ error: `Balans yetarli emas — yana ${money(price - balance)} kerak.`, need: price - balance });
  }
  const orderId = Number(run(
    "INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, 'diss', ?, 0, ?)",
    req.user.id, JSON.stringify(params), nowStr(),
  ).lastInsertRowid);
  res.status(201).json({ orderId });
}));

// ===== Rasmlar (imzolangan havola) =====
export const dissMediaRouter = Router();

dissMediaRouter.get('/diss-media/:token/:name', (req, res) => {
  const parts = readToken(req.params.token);
  const { name } = req.params;
  if (!parts || parts[0] !== 'smedia' || !SAFE_NAME.test(name) || !/\.(png|jpg)$/i.test(name)) return res.status(403).end();
  const file = path.join(folder(Number(parts[1])), name);
  if (!existsSync(file)) return res.status(404).end();
  res.sendFile(file, { maxAge: '1h', headers: { 'X-Content-Type-Options': 'nosniff' } });
});

export default router;
