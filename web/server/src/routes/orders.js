import express, { Router } from 'express';

import { all, nowStr, one, run } from '../db.js';
import { ARTICLE_TYPES, ORDER_KINDS, getSettings, money, orderPrice } from '../settings.js';
import { RECEIPT_LIMIT, queueReceipt, receiptBlocked, storeReceipt } from './payments.js';

const router = Router();

const TOPIC_MIN = 3;
const TOPIC_MAX = 200;
const AUTHOR_MAX = 70;
const clean = (value) => String(value ?? '').split(/\s+/).filter(Boolean).join(' ');

/** Buyurtma parametrlarini bot qoidalari bo'yicha tekshiradi: [params, xato] qaytaradi. */
function validate(kind, body, settings) {
  const topic = clean(body.topic);
  if (topic.length < TOPIC_MIN || topic.length > TOPIC_MAX) {
    return [null, `Mavzu ${TOPIC_MIN}–${TOPIC_MAX} belgi oralig'ida bo'lsin.`];
  }
  if (!(body.lang in settings.languages)) return [null, 'Tilni tanlang.'];
  const native = kind === 'pres' ? 'pptx' : 'docx';
  const fmt = body.fmt === 'pdf' && settings.pdf ? 'pdf' : native;

  if (kind === 'pres') {
    const { plan_min: planMin, plan_max: planMax, fixed, options } = settings.slides;
    const plans = Number(body.plans);
    const slides = Number(body.slides);
    if (!Number.isInteger(plans) || plans < planMin || plans > planMax) {
      return [null, `Reja soni ${planMin}–${planMax} oralig'ida bo'lsin.`];
    }
    if (!Number.isInteger(slides) || slides < plans + fixed || slides > options.at(-1)) {
      return [null, `Slaydlar soni ${plans + fixed}–${options.at(-1)} oralig'ida bo'lsin.`];
    }
    if (!(body.theme in settings.themes)) return [null, 'Dizaynni tanlang.'];
    const author = clean(body.author);
    if (author.length > AUTHOR_MAX) return [null, `Muallif ismi ${AUTHOR_MAX} belgidan oshmasin.`];
    return [{ topic, plans, slides, lang: body.lang, theme: body.theme, author, fmt }, null];
  }

  if (kind === 'maqola') {
    if (!ARTICLE_TYPES.includes(body.type)) return [null, 'Maqola turini tanlang.'];
    const { words_min: min, words_max: max } = settings.article;
    const words = Number(body.words);
    if (!Number.isInteger(words) || words < min || words > max) return [null, `So'zlar soni ${min}–${max} oralig'ida bo'lsin.`];
    const style = ['auto', 'academic', 'simple'].includes(body.style) ? body.style : 'auto';
    const purpose = clean(body.purpose);
    const notes = clean(body.notes);
    const author = clean(body.author);
    if (purpose.length > 200) return [null, "Maqsad 200 belgidan oshmasin."];
    if (notes.length > 600) return [null, "Qo'shimcha talablar 600 belgidan oshmasin."];
    if (author.length > 200) return [null, 'Muallif 200 belgidan oshmasin.'];
    // ui — chatga keladigan xabar tili (ilova tili), lang — maqola matni tili
    const ui = ['uz', 'ru', 'en'].includes(body.ui) ? body.ui : body.lang;
    return [{ type: body.type, topic, lang: body.lang, words, style, purpose, notes, author, source: 'web', ui }, null];
  }

  // Betlar soni — tugmalardagi variant yoki foydalanuvchi o'zi yozgan son (bot bilan bir xil oraliq: config.PAGE_RANGE)
  const pages = Number(body.pages);
  const [low, high] = settings.page_range?.[kind] ?? [settings.pages[kind][0], settings.pages[kind].at(-1)];
  if (!Number.isInteger(pages) || pages < low || pages > high) return [null, `Betlar soni ${low}–${high} oralig'ida bo'lsin.`];
  return [{ topic, pages, lang: body.lang, fmt }, null];
}

const balanceOf = (userId) => one('SELECT balance FROM users WHERE id = ?', userId)?.balance ?? 0;
const BUSY_TEXT = "Oldingi buyurtmangiz hali tayyorlanmoqda yoki to'lovi tekshiruvda, biroz kuting.";

// To'lov kutayotgan, lekin cheki yuborilmagan (yoki chek hali navbatda bo'lmagan) buyurtma — bot bilan bir xil
const UNPAID =
  "status = 'awaiting_payment' AND id NOT IN (SELECT order_id FROM payments WHERE order_id IS NOT NULL AND status = 'pending') " +
  "AND id NOT IN (SELECT CAST(json_extract(params, '$.order_id') AS INTEGER) FROM web_orders " +
  "WHERE kind = 'receipt' AND status IN ('pending', 'working') AND json_extract(params, '$.order_id') IS NOT NULL)";

/** Tayyorlanayotgan yoki cheki tekshiruvdagi buyurtma — bir vaqtda bittadan. */
export function waitingOrder(userId) {
  return one(
    "SELECT id, kind, status FROM web_orders WHERE user_id = ? AND kind NOT IN ('edit', 'import', 'receipt', 'ai', 'diplom', 'diss', 'pay_review', 'admins') AND " +
      `(status IN ('pending', 'working') OR (status = 'awaiting_payment' AND NOT (${UNPAID})))`,
    userId,
  );
}

// ===== Yangi buyurtma — bot navbatdan olib bajaradi (handlers/web.py) =====
router.post('/orders', (req, res) => {
  const kind = req.body?.kind;
  if (!ORDER_KINDS.includes(kind)) return res.status(400).json({ error: "Noma'lum xizmat." });
  const settings = getSettings();
  const [params, error] = validate(kind, req.body, settings);
  if (error) return res.status(400).json({ error });

  const userId = req.user.id;
  const busy = waitingOrder(userId);
  if (busy) return res.status(409).json({ error: BUSY_TEXT, orderId: busy.id });
  const price = orderPrice(userId, kind, params, settings);
  const balance = balanceOf(userId);
  if (balance < price) {
    return res.status(402).json({
      error: `Balans yetarli emas — yana ${money(price - balance)} kerak.`,
      need: price - balance,
    });
  }

  const { lastInsertRowid } = run(
    'INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, ?, ?, ?, ?)',
    userId, kind, JSON.stringify(params), price, nowStr(),
  );
  res.status(201).json({ id: Number(lastInsertRowid), price });
});

// ===== Buyurtma uchun to'lov: buyurtma + chek bitta so'rovda =====
// Buyurtma «to'lov kutilmoqda» bo'lib saqlanadi, chek bot orqali adminga boradi.
// Admin ✅ bosgach — bot buyurtmani navbatga qo'yadi, tayyorlab userga yuboradi (prezentatsiya_bot/handlers/wallet.py)
const ORDER_PAY_MIN = 1000; // bot bilan bir xil

router.post('/orders/checkout', express.raw({ type: () => true, limit: RECEIPT_LIMIT }), (req, res) => {
  let body;
  try {
    body = JSON.parse(decodeURIComponent(req.get('X-Order') || ''));
  } catch {
    return res.status(400).json({ error: "Buyurtma ma'lumoti buzilgan." });
  }
  const kind = body?.kind;
  if (!ORDER_KINDS.includes(kind)) return res.status(400).json({ error: "Noma'lum xizmat." });
  const settings = getSettings();
  const [params, error] = validate(kind, body, settings);
  if (error) return res.status(400).json({ error });

  const userId = req.user.id;
  const busy = waitingOrder(userId);
  if (busy) return res.status(409).json({ error: BUSY_TEXT, orderId: busy.id });
  const blocked = receiptBlocked(userId);
  if (blocked) return res.status(409).json({ error: blocked });
  const price = orderPrice(userId, kind, params, settings);
  const need = price - balanceOf(userId);
  if (need <= 0) return res.status(400).json({ error: "Balansingiz yetarli — «Yaratish» ni bosing." });

  const receipt = storeReceipt(userId, req.body);
  if (receipt.error) return res.status(receipt.status).json({ error: receipt.error });
  const amount = Math.max(need, ORDER_PAY_MIN);
  // Cheki yuborilmagan eski «to'lov kutilmoqda» buyurtmasi bo'lsa — yangisi uning o'rnini oladi
  run(
    "UPDATE web_orders SET status = 'failed', error = 'Yangi buyurtma bilan almashtirildi.', finished_at = ? " +
      `WHERE user_id = ? AND ${UNPAID}`,
    nowStr(), userId,
  );
  const orderId = Number(run(
    "INSERT INTO web_orders (user_id, kind, params, price, status, created_at) VALUES (?, ?, ?, ?, 'awaiting_payment', ?)",
    userId, kind, JSON.stringify(params), price, nowStr(),
  ).lastInsertRowid);
  queueReceipt(userId, amount, receipt, orderId);
  res.status(201).json({ id: orderId, amount, price });
});

// ===== Buyurtma holati (ilova har 2–3 soniyada so'raydi) =====
router.get('/orders/:id(\\d+)', (req, res) => {
  const order = one(
    'SELECT o.id, o.kind, o.params, o.price, o.status, o.error, o.document_id, o.created_at, o.finished_at, ' +
      'd.title AS document_title FROM web_orders o LEFT JOIN documents d ON d.id = o.document_id ' +
      'WHERE o.id = ? AND o.user_id = ?',
    Number(req.params.id), req.user.id,
  );
  if (!order) return res.status(404).json({ error: 'Buyurtma topilmadi.' });
  const ahead = order.status === 'pending' && order.kind !== 'edit'
    ? one("SELECT COUNT(*) AS n FROM web_orders WHERE status = 'pending' AND kind NOT IN ('edit', 'import', 'receipt', 'ai', 'diplom', 'diss', 'pay_review', 'admins') AND id < ?", order.id).n
    : 0;
  res.json({ ...order, params: JSON.parse(order.params), ahead });
});

router.get('/orders', (req, res) => {
  const orders = all(
    "SELECT id, kind, params, price, status, error, created_at FROM web_orders WHERE user_id = ? AND kind NOT IN ('edit', 'import', 'receipt', 'ai', 'diplom', 'diss', 'pay_review', 'admins') " +
      'ORDER BY id DESC LIMIT 10',
    req.user.id,
  );
  res.json({ orders: orders.map((o) => ({ ...o, params: JSON.parse(o.params) })) });
});

export default router;
