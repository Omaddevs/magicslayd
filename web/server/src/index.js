import { existsSync } from 'node:fs';
import path from 'node:path';

import express from 'express';

import { auth, requireAccount } from './auth.js';
import { CLIENT_DIST, DB_PATH, DEV_USER_ID, PORT } from './config.js';
import { rateLimit } from './rateLimit.js';
import account from './routes/account.js';
import adminRoutes from './routes/admin.js';
import articles, { articlePublicRouter } from './routes/articles.js';
import assistant, { aiFileRouter } from './routes/assistant.js';
import authRoutes from './routes/auth.js';
import decks, { mediaRouter } from './routes/decks.js';
import diplomas, { diplomaMediaRouter } from './routes/diplomas.js';
import dissertations, { dissMediaRouter } from './routes/dissertations.js';
import { linkRouter, publicRouter } from './routes/download.js';
import materials from './routes/materials.js';
import news, { newsMediaRouter } from './routes/news.js';
import notifications from './routes/notifications.js';
import orders from './routes/orders.js';
import papers, { paperMediaRouter } from './routes/papers.js';
import payments from './routes/payments.js';

const app = express();
app.disable('x-powered-by');
// Proksi (cloudflared / Caddy) orqasida userning haqiqiy IP'si — limitlar har bir userga alohida bo'lishi uchun.
// Docker'da Caddy boshqa konteynerda: TRUST_PROXY=loopback,uniquelocal (docker-compose.yml)
app.set('trust proxy', (process.env.TRUST_PROXY || 'loopback').split(',').map((s) => s.trim()));

// Muharrirlar o'z chegaralari bilan o'qiydi (katta taqdimot / referat, rasm, video) — qolganlari uchun kichik chegara
const smallJson = express.json({ limit: '50kb' });
const ownBody = (url) => ['/api/decks/', '/api/papers/', '/api/diplomas/', '/api/dissertations', '/api/articles/'].some((p) => url.startsWith(p));
app.use((req, res, next) => (ownBody(req.path) ? next() : smallJson(req, res, next)));

// ===== API =====
app.get('/api/health', (req, res) => res.json({ ok: true }));
// Imzolangan havolalar (yuklab olish, rasm/video) — Authorization'siz
app.use('/api', publicRouter, mediaRouter, paperMediaRouter, diplomaMediaRouter, dissMediaRouter, aiFileRouter, newsMediaRouter, articlePublicRouter);
// Ro'yxatdan o'tish / kirish / parolni tiklash — o'z tekshiruvlari bilan
app.use('/api/auth', authRoutes);
// Qolgani — Telegram initData yoki sessiya bilan. Mehmon faqat ko'radi (requireAccount)
app.use('/api', auth, requireAccount, rateLimit, account, orders, materials, linkRouter, decks, papers, articles, diplomas, dissertations, payments, assistant, news, notifications, adminRoutes);
app.use('/api', (req, res) => res.status(404).json({ error: 'Topilmadi.' }));

// Kutilmagan xatolar — foydalanuvchiga ichki tafsilot ko'rsatilmaydi
app.use((error, req, res, next) => {
  if (res.headersSent) return next(error);
  if (error.type === 'entity.too.large') {
    return res.status(413).json({ error: 'Fayl yoki matn juda katta. Rasm — 10 MB, video — 25 MB gacha.' });
  }
  if (error.status === 400) return res.status(400).json({ error: "So'rov noto'g'ri." });
  console.error(error);
  res.status(500).json({ error: "Serverda xato yuz berdi. Qayta urinib ko'ring." });
});

// ===== Build qilingan React ilova (production) =====
if (existsSync(CLIENT_DIST)) {
  // index.html keshlanmaydi (yangilanish darhol ko'rinsin), assets/ — nomi hash bilan, uzoq keshlanadi
  app.use('/assets', express.static(path.join(CLIENT_DIST, 'assets'), { maxAge: '365d', immutable: true }));
  app.use(express.static(CLIENT_DIST, { index: false, maxAge: '1d' }));
  app.get('*', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache');
    res.sendFile(path.join(CLIENT_DIST, 'index.html'));
  });
}

app.listen(PORT, () => {
  console.log(`Slayd web server: http://localhost:${PORT}`);
  console.log(`Baza: ${DB_PATH}`);
  if (DEV_USER_ID) console.log(`⚠️ DEV rejim: shu kompyuterdan Telegram'siz so'rovlar ${DEV_USER_ID} user nomidan bajariladi`);
});
