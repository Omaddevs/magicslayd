import { readFileSync } from 'node:fs';

import { Router } from 'express';

import { all, nowStr, one, run } from '../db.js';
import { escapeHtml, telegramReason, tg, tgSendFile } from '../telegram.js';
import { isEditable } from './decks.js';
import { fileName, localFile } from './download.js';
import { isArticle } from './articles.js';
import { isPaper } from './papers.js';

const router = Router();

const MATERIAL_KINDS = ['pres', 'referat', 'mustaqil', 'kurs', 'shablon'];
const KIND_LABELS = { pres: 'Taqdimot', referat: 'Referat', mustaqil: 'Mustaqil ish', kurs: 'Kurs ishi', shablon: 'Shablon' };
const MATERIAL_FIELDS = 'm.id, m.kind, m.title, m.pages, m.file_type, m.downloads, m.created_at';

const likeArg = (q) => `%${q.replace(/[\\%_]/g, (c) => `\\${c}`)}%`;

/** Har qanday hujjat ochiladi: loyihasi bo'lmasa muharrir uni fayldan tiklaydi (ready — loyiha tayyor). */
const withEditable = (doc) => ({
  ...doc, editable: true,
  ready: doc.kind === 'diplom' || doc.kind === 'diss' || (doc.kind === 'maqola' ? isArticle(doc.id)
    : doc.kind === 'pres' ? isEditable(doc.id) : isPaper(doc.id)),
});

// ===== Ommabop materiallar (admin bot orqali qo'shadi: /ommabop) =====
router.get('/materials', (req, res) => {
  const q = String(req.query.q ?? '').trim().slice(0, 100);
  const kind = MATERIAL_KINDS.includes(req.query.kind) ? req.query.kind : null;
  const limit = Math.min(Number(req.query.limit) || 20, 50);
  const where = ['1 = 1'];
  const args = [req.account ? req.user.id : 0];
  if (q) {
    where.push("m.title LIKE ? ESCAPE '\\'");
    args.push(likeArg(q));
  }
  if (kind) {
    where.push('m.kind = ?');
    args.push(kind);
  }
  const materials = all(
    `SELECT ${MATERIAL_FIELDS}, b.user_id IS NOT NULL AS saved FROM materials m ` +
      'LEFT JOIN web_bookmarks b ON b.material_id = m.id AND b.user_id = ? ' +
      `WHERE ${where.join(' AND ')} ORDER BY m.downloads DESC, m.id DESC LIMIT ?`,
    ...args, limit,
  );
  res.json({ materials });
});

async function sendToChat(res, chatId, fileId, caption) {
  try {
    await tg('sendDocument', { chat_id: chatId, document: fileId, caption, parse_mode: 'HTML' });
    return true;
  } catch (error) {
    res.status(502).json({ error: telegramReason(error) });
    return false;
  }
}

// Fayl userning Telegram chatiga yuboriladi — Mini App ichida eng ishonchli «yuklab olish»
router.post('/materials/:id(\\d+)/send', async (req, res) => {
  const material = one('SELECT * FROM materials WHERE id = ?', Number(req.params.id));
  if (!material) return res.status(404).json({ error: 'Material topilmadi.' });
  const caption = `📚 ${escapeHtml(material.title)}\n${KIND_LABELS[material.kind] ?? ''}`;
  if (await sendToChat(res, req.user.id, material.file_id, caption)) {
    run('UPDATE materials SET downloads = downloads + 1 WHERE id = ?', material.id);
    res.json({ ok: true });
  }
});

router.post('/materials/:id(\\d+)/bookmark', (req, res) => {
  const id = Number(req.params.id);
  if (!one('SELECT 1 FROM materials WHERE id = ?', id)) return res.status(404).json({ error: 'Material topilmadi.' });
  const removed = run('DELETE FROM web_bookmarks WHERE user_id = ? AND material_id = ?', req.user.id, id).changes;
  if (!removed) {
    run('INSERT INTO web_bookmarks (user_id, material_id, created_at) VALUES (?, ?, ?)', req.user.id, id, nowStr());
  }
  res.json({ saved: !removed });
});

// ===== Saqlangan: botda yaratilgan hujjatlar + belgilangan materiallar =====
router.get('/saved', (req, res) => {
  const documents = all(
    'SELECT id, kind, title, created_at FROM documents WHERE user_id = ? ORDER BY id DESC LIMIT 50',
    req.user.id,
  ).map(withEditable);
  const bookmarks = all(
    `SELECT ${MATERIAL_FIELDS}, 1 AS saved FROM web_bookmarks b JOIN materials m ON m.id = b.material_id ` +
      'WHERE b.user_id = ? ORDER BY b.created_at DESC',
    req.user.id,
  );
  res.json({ documents, bookmarks });
});

router.post('/documents/:id(\\d+)/send', async (req, res) => {
  const doc = one('SELECT * FROM documents WHERE id = ? AND user_id = ?', Number(req.params.id), req.user.id);
  if (!doc) return res.status(404).json({ error: 'Fayl topilmadi.' });
  const caption = `📂 ${escapeHtml(doc.title)}\n🕘 ${doc.created_at}`;
  const local = localFile('documents', doc.id);
  if (!local) {
    if (await sendToChat(res, req.user.id, doc.file_id, caption)) res.json({ ok: true });
    return;
  }
  // Muharrirda tahrirlangan — diskdagi yangi versiya yuklanadi. Yangi file_id saqlanadi,
  // shunda botdagi «📂 Hujjatlarim» ham yangi versiyani beradi
  try {
    const fileId = await tgSendFile(req.user.id, readFileSync(local.file), fileName(doc.title, local.ext), `✏️ ${caption}`);
    run('UPDATE documents SET file_id = ? WHERE id = ?', fileId, doc.id);
    res.json({ ok: true });
  } catch (error) {
    res.status(502).json({ error: telegramReason(error) });
  }
});

// ===== Qidiruv: materiallar + o'z hujjatlari =====
router.get('/search', (req, res) => {
  const q = String(req.query.q ?? '').trim().slice(0, 100);
  if (q.length < 2) return res.json({ materials: [], documents: [] });
  const pattern = likeArg(q);
  const materials = all(
    `SELECT ${MATERIAL_FIELDS}, b.user_id IS NOT NULL AS saved FROM materials m ` +
      'LEFT JOIN web_bookmarks b ON b.material_id = m.id AND b.user_id = ? ' +
      "WHERE m.title LIKE ? ESCAPE '\\' ORDER BY m.downloads DESC LIMIT 20",
    req.account ? req.user.id : 0, pattern,
  );
  // Mehmon (hisobga kirmagan) — faqat ommabop materiallar
  const documents = !req.account ? [] : all(
    "SELECT id, kind, title, created_at FROM documents WHERE user_id = ? AND title LIKE ? ESCAPE '\\' " +
      'ORDER BY id DESC LIMIT 20',
    req.user.id, pattern,
  ).map(withEditable);
  res.json({ materials, documents });
});

export default router;
