import crypto from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { Router } from 'express';

import { DB_PATH } from '../config.js';
import { nowStr, one, run } from '../db.js';
import { checkLimits, validateAiRequest } from '../aiRules.js';
import { getSettings } from '../settings.js';
import { makeToken, readToken } from '../signed.js';

// AI yordamchi. So'rov navbatga qo'yiladi (web_orders, kind = 'ai'), bot umumiy servis orqali bajaradi
// (prezentatsiya_bot/assistant/service.py) va natijani ai/<vazifa_id>/ ga yozadi.
// Javob uzoq (15–90 s) bo'lgani uchun endpoint darhol jobId qaytaradi, ilova holatni so'rab turadi —
// proksi/Cloudflare'ning 100 soniyalik chegarasiga urilmaydi.
const AI_DIR = path.join(path.dirname(DB_PATH), 'ai');
const FILE_TTL = 2 * 60 * 60;
const MIME = {
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
};
const COUNTED = "('queued', 'working', 'ok')"; // xato bilan tugaganlari limitga kirmaydi

const router = Router();

// Telegram user_id bo'yicha; ilova har doim Telegram orqali kiradi, bo'lmasa IP bo'yicha
const userKey = (req) => (req.user?.id ? `tg:${req.user.id}` : `ip:${req.ip}`);
const userTag = (key) => crypto.createHash('sha256').update(key).digest('hex').slice(0, 10);

function stamp(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function usage(key) {
  const now = new Date();
  const today = one(
    `SELECT COUNT(*) AS n FROM ai_requests WHERE user_key = ? AND created_at >= ? AND status IN ${COUNTED}`,
    key, stamp(now).slice(0, 10),
  ).n;
  const recent = one(
    'SELECT COUNT(*) AS n FROM ai_requests WHERE user_key = ? AND created_at >= ?', key, stamp(new Date(now - 60_000)),
  ).n;
  return { today, recent };
}

/** Har bir so'rov logi: vaqt, user (xesh), ish turi, holat. Mavzu, kalit va shaxsiy ma'lumot yozilmaydi. */
function logRequest(key, type, status, code) {
  console.log(JSON.stringify({ time: new Date().toISOString(), event: 'ai_request', user: userTag(key), type, status, code }));
}

router.get('/ai/limits', (req, res) => {
  const rules = getSettings().ai;
  const { today } = usage(userKey(req));
  res.json({ limit: rules.daily_limit, used: today, left: Math.max(0, rules.daily_limit - today) });
});

router.post('/ai/generate', (req, res) => {
  const rules = getSettings().ai;
  const key = userKey(req);
  const checked = validateAiRequest(req.body, rules);
  if (checked.error) {
    logRequest(key, req.body?.type ?? null, 'rejected', 'validation');
    return res.status(400).json({ error: checked.error, field: checked.field });
  }
  const { params } = checked;
  const { today, recent } = usage(key);
  const blocked = checkLimits(today, recent, rules);
  if (blocked) {
    logRequest(key, params.type, 'rejected', blocked.code);
    return res.status(blocked.status).json({ error: blocked.error, code: blocked.code });
  }

  const requestId = Number(run(
    "INSERT INTO ai_requests (user_key, source, kind, status, created_at) VALUES (?, 'web', ?, 'queued', ?)",
    key, params.type, stamp(),
  ).lastInsertRowid);
  const jobId = Number(run(
    "INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, 'ai', ?, 0, ?)",
    req.user.id, JSON.stringify({ ...params, request_id: requestId }), nowStr(),
  ).lastInsertRowid);
  logRequest(key, params.type, 'queued');
  res.status(202).json({ jobId, left: Math.max(0, rules.daily_limit - today - 1) });
});

function readResult(jobId) {
  try {
    return JSON.parse(readFileSync(path.join(AI_DIR, String(jobId), 'result.json'), 'utf8'));
  } catch {
    return null;
  }
}

router.get('/ai/jobs/:id(\\d+)', (req, res) => {
  const job = one("SELECT id, status, error FROM web_orders WHERE id = ? AND user_id = ? AND kind = 'ai'",
    Number(req.params.id), req.user.id);
  if (!job) return res.status(404).json({ error: 'So\'rov topilmadi.' });
  if (job.status === 'failed') return res.json({ status: 'failed', error: job.error });
  if (job.status !== 'done') return res.json({ status: job.status });
  const saved = readResult(job.id);
  if (!saved) return res.json({ status: 'failed', error: "Natija muddati o'tgan. Qayta yarating." });
  res.json({
    status: 'done',
    result: saved.result,
    files: saved.files.map((file) => ({
      ...file,
      url: `/api/ai/file/${makeToken(['ai', job.id, req.user.id, file.ext], FILE_TTL)}`,
    })),
  });
});

// ===== Fayl (imzolangan havola — Telegram.downloadFile va <a download> uchun) =====
export const aiFileRouter = Router();

aiFileRouter.get('/ai/file/:token', (req, res) => {
  const parts = readToken(req.params.token);
  if (!parts || parts[0] !== 'ai' || !MIME[parts[3]]) {
    return res.status(403).send("Havola eskirgan. AI yordamchi sahifasidan qayta yuklab oling.");
  }
  const [, jobId, , ext] = parts;
  const file = path.join(AI_DIR, String(Number(jobId)), `file.${ext}`);
  const saved = readResult(Number(jobId));
  if (!existsSync(file) || !saved) return res.status(404).send("Fayl muddati o'tgan. Qayta yarating.");
  const name = saved.files.find((f) => f.ext === ext)?.name ?? `hujjat.${ext}`;
  res.setHeader('Content-Type', MIME[ext]);
  res.setHeader('Content-Disposition', `attachment; filename="${name}"; filename*=UTF-8''${encodeURIComponent(name)}`);
  res.setHeader('Cache-Control', 'no-store');
  res.sendFile(file);
});

export default router;
