import { randomUUID } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import express, { Router } from 'express';

import { DB_PATH } from '../config.js';
import { all, nowStr, one, run } from '../db.js';
import { getSettings, money } from '../settings.js';

// Hisobni to'ldirish (ilova ichida). Bot chatidagi to'lov bilan bitta tizim: chek bot orqali adminga boradi,
// admin botda ✅/❌ bosadi, summa o'sha «payments» jadvali orqali balansga tushadi (handlers/wallet.py)
const RECEIPTS_DIR = path.join(path.dirname(DB_PATH), 'receipts');
const RECEIPT_MAX = 10 * 1024 * 1024;

const router = Router();

/** Chekni tekshirib diskka saqlaydi: { file, type } yoki { error, status }. */
export function storeReceipt(userId, data) {
  if (!Buffer.isBuffer(data) || data.length < 100) return { error: 'Chek faylini tanlang.', status: 400 };
  let ext = null;
  if (data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) ext = 'jpg';
  else if (data.subarray(0, 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47]))) ext = 'png';
  else if (data.subarray(0, 4).toString('latin1') === '%PDF') ext = 'pdf';
  if (!ext) return { error: "Chekni rasm (JPG, PNG) yoki PDF ko'rinishida yuklang.", status: 415 };
  mkdirSync(RECEIPTS_DIR, { recursive: true });
  const file = `chek-${userId}-${randomUUID().slice(0, 8)}.${ext}`;
  writeFileSync(path.join(RECEIPTS_DIR, file), data);
  return { file, type: ext === 'pdf' ? 'document' : 'photo' };
}

/** Chek tekshiruvi mumkinmi (to'lov sozlangan, kutilayotgan cheklar limitdan oshmagan). Xato matni yoki null. */
export function receiptBlocked(userId) {
  const pay = getSettings().payment;
  if (!pay?.enabled) return "To'lov hozircha sozlanmagan. Birozdan so'ng urinib ko'ring.";
  if (pendingCount(userId) >= pay.pending_max) {
    return `Sizda ${pay.pending_max} ta chek tekshiruvda turibdi. Admin tasdiqlashini kuting 🙏`;
  }
  return null;
}

export const RECEIPT_LIMIT = RECEIPT_MAX;

export function queueReceipt(userId, amount, receipt, orderId = null) {
  return Number(run(
    "INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, 'receipt', ?, 0, ?)",
    userId, JSON.stringify({ amount, file: receipt.file, type: receipt.type, order_id: orderId }), nowStr(),
  ).lastInsertRowid);
}

function pendingCount(userId) {
  const payments = one("SELECT COUNT(*) AS n FROM payments WHERE user_id = ? AND status = 'pending'", userId).n;
  const queued = one(
    "SELECT COUNT(*) AS n FROM web_orders WHERE user_id = ? AND kind = 'receipt' AND status IN ('pending', 'working')",
    userId,
  ).n;
  return payments + queued;
}

// Oxirgi to'lovlar va ularning holati (tekshiruvda / tasdiqlandi / rad etildi)
router.get('/payments', (req, res) => {
  const payments = all(
    'SELECT id, amount, status, created_at, reviewed_at FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT 10',
    req.user.id,
  );
  res.json({
    payments,
    pending: pendingCount(req.user.id),
    balance: one('SELECT balance FROM users WHERE id = ?', req.user.id)?.balance ?? 0,
  });
});

// Chek yuborish: xom fayl (rasm yoki PDF), summa — X-Amount sarlavhasida
router.post('/payments', express.raw({ type: () => true, limit: RECEIPT_MAX }), (req, res) => {
  const pay = getSettings().payment;
  const blocked = receiptBlocked(req.user.id);
  if (blocked) return res.status(pay?.enabled ? 409 : 503).json({ error: blocked });

  const amount = Number(req.get('X-Amount'));
  if (!Number.isInteger(amount) || amount < pay.min || amount > pay.max) {
    return res.status(400).json({ error: `Summa ${money(pay.min)} dan ${money(pay.max)} gacha bo'lsin.` });
  }
  const receipt = storeReceipt(req.user.id, req.body);
  if (receipt.error) return res.status(receipt.status).json({ error: receipt.error });
  res.status(201).json({ orderId: queueReceipt(req.user.id, amount, receipt) });
});

export default router;
