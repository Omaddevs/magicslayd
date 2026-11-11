import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { Router } from 'express';

import { BOT_TOKEN, DECKS_DIR } from '../config.js';
import { one, run } from '../db.js';
import { makeToken, readToken } from '../signed.js';
import { telegramReason, tg } from '../telegram.js';
import { localPaperFile } from './papers.js';

// Saytdan to'g'ridan-to'g'ri yuklab olish.
// Telegram.WebApp.downloadFile va oddiy <a href> sarlavha (Authorization) yubora olmaydi,
// shuning uchun avval qisqa muddatli imzolangan havola beriladi, fayl o'sha havola orqali yuklanadi
const LINK_TTL = 10 * 60; // soniya
const MIME = {
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
};

/** Faylni topadi: material hammaga ochiq, hujjat — faqat egasiga. */
function findFile(source, id, userId) {
  if (source === 'materials') return one('SELECT id, kind, title, file_id, file_type FROM materials WHERE id = ?', id);
  if (source === 'documents') {
    return one('SELECT id, kind, title, file_id FROM documents WHERE id = ? AND user_id = ?', id, userId);
  }
  return undefined;
}

/** Muharrirda tahrirlangan taqdimot yoki ishning eng oxirgi versiyasi (diskda): { file, ext } yoki null. */
export function localFile(source, id) {
  if (source !== 'documents') return null;
  const file = path.join(DECKS_DIR, String(id), 'file.pptx');
  return existsSync(file) ? { file, ext: 'pptx' } : localPaperFile(id);
}

async function fetchTelegramFile(fileId) {
  const { file_path: filePath } = await tg('getFile', { file_id: fileId });
  const response = await fetch(`https://api.telegram.org/file/bot${BOT_TOKEN}/${filePath}`, {
    signal: AbortSignal.timeout(60_000),
  });
  if (!response.ok) throw new Error(`Telegram fayl: ${response.status}`);
  return { filePath, data: Buffer.from(await response.arrayBuffer()) };
}

/** Fayl turini ichidan aniqlaydi — Telegram yo'lida kengaytma bo'lmaydi («documents/file_0»). */
function sniff(data) {
  if (data.subarray(0, 4).toString('latin1') === '%PDF') return 'pdf';
  if (data.subarray(0, 2).toString('latin1') !== 'PK') return null;
  // Office fayllari — zip: ichidagi papka nomlari fayl oxiridagi ro'yxatda ochiq yoziladi
  const names = data.subarray(Math.max(0, data.length - 65_536)).toString('latin1');
  if (names.includes('ppt/')) return 'pptx';
  if (names.includes('word/')) return 'docx';
  if (names.includes('xl/')) return 'xlsx';
  return null;
}

// file_id → kengaytma (havola berishda aniqlangani yuklab olishda qayta hisoblanmaydi)
const typeCache = new Map();

async function detectType(file) {
  if (typeCache.has(file.file_id)) return typeCache.get(file.file_id);
  const { filePath, data } = await fetchTelegramFile(file.file_id);
  const ext = path.extname(filePath).slice(1).toLowerCase() || sniff(data)
    || file.file_type || (file.kind === 'pres' ? 'pptx' : 'docx');
  if (typeCache.size > 1000) typeCache.delete(typeCache.keys().next().value);
  typeCache.set(file.file_id, ext);
  return ext;
}

export function fileName(title, ext) {
  const base = title.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, '_').slice(0, 60) || 'hujjat';
  return `${base}.${ext}`;
}

// ===== 1) Havola olish (Authorization bilan) =====
export const linkRouter = Router();

linkRouter.post('/:source(materials|documents)/:id(\\d+)/link', async (req, res) => {
  const { source } = req.params;
  const file = findFile(source, Number(req.params.id), req.user.id);
  if (!file) return res.status(404).json({ error: 'Fayl topilmadi.' });
  try {
    const ext = localFile(source, file.id)?.ext ?? await detectType(file);
    res.json({
      url: `/api/download/${makeToken(['dl', source, file.id, req.user.id], LINK_TTL)}`,
      fileName: fileName(file.title, ext),
    });
  } catch (error) {
    res.status(502).json({ error: telegramReason(error) });
  }
});

// ===== 2) Faylning o'zi (imzolangan havola orqali, Authorization'siz) =====
export const publicRouter = Router();

publicRouter.get('/download/:token', async (req, res) => {
  const parts = readToken(req.params.token);
  if (!parts || parts[0] !== 'dl') return res.status(403).send("Havola eskirgan. Ilovada qaytadan «Yuklab olish» ni bosing.");
  const [, source, id, userId] = parts;
  const file = findFile(source, Number(id), Number(userId));
  if (!file) return res.status(404).send('Fayl topilmadi.');

  try {
    let data;
    let ext;
    const local = localFile(source, file.id);
    if (local) {
      data = readFileSync(local.file);
      ext = local.ext;
    } else {
      const fetched = await fetchTelegramFile(file.file_id);
      data = fetched.data;
      ext = typeCache.get(file.file_id) || path.extname(fetched.filePath).slice(1).toLowerCase() || sniff(data)
        || (file.kind === 'pres' ? 'pptx' : 'docx');
    }
    const name = fileName(file.title, ext);
    res.setHeader('Content-Type', MIME[ext] ?? 'application/octet-stream');
    res.setHeader(
      'Content-Disposition',
      // Eski brauzerlar uchun lotincha nom, yangilari uchun — asl (kirill ham) nom
      `attachment; filename="${name.replace(/[^\w.-]/g, '_')}"; filename*=UTF-8''${encodeURIComponent(name)}`,
    );
    res.setHeader('Cache-Control', 'no-store');
    if (source === 'materials') run('UPDATE materials SET downloads = downloads + 1 WHERE id = ?', file.id);
    res.send(data);
  } catch (error) {
    console.error(error);
    res.status(502).send(telegramReason(error));
  }
});
