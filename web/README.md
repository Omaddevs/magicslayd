# MagicSlayd Web — Telegram Mini App

MagicSlayd boti uchun web ilova: **React + Vite** (client) va **Node.js + Express** (server).
Ilova bot bilan bitta bazada (`bot.db`) ishlaydi — balans, hujjatlar, titul ma'lumotlari umumiy.

```
magicslayd/
├── bot/                      ← bot (Python, aiogram)
│   └── handlers/web.py       ← ilova buyurtmalarini bajaradi
├── data/                     ← bot.db va loyihalar (umumiy)
└── web/                      ← shu loyiha
    ├── client/               ← React + Vite (UI)
    └── server/               ← Node.js API
```

## Qanday bog'langan

| Ilovada | Qayerda bajariladi |
|---|---|
| Kirish | Telegram `initData` imzosi botning `BOT_TOKEN` i bilan tekshiriladi |
| Balans, tarix | `users`, `transactions` jadvallari (bot bilan umumiy) |
| Buyurtma (taqdimot, referat, kurs, mustaqil ish) | Server `web_orders` ga yozadi → bot navbatdan olib AI bilan yasaydi → fayl **Telegram chatga** keladi va «Saqlangan» da chiqadi |
| Hisobni to'ldirish | Bot chatiga «➕ Hisobni to'ldirish» tugmali xabar yuboriladi (chek bot orqali) |
| Titul ma'lumotlari | `titles` jadvali — botdagi «👤 Titul ma'lumotlari» bilan bir xil |
| Ommabop materiallar | `materials` jadvali — admin botda `/ommabop` bilan qo'shadi |
| Narxlar, dizaynlar, tillar | Bot ishga tushganda `meta` jadvaliga yozadi (yagona manba — `config.py`) |
| AI yordamchi | Server limitni tekshirib `web_orders` (kind `ai`) ga yozadi → bot umumiy servis (`bot/assistant/`) orqali bajaradi → natija va fayllar `ai/<id>/` da 24 soat. Botdagi «🤖 AI yordamchi» ham shu servisdan foydalanadi |

Pul **bot tomonida** yechiladi va xato bo'lsa qaytariladi — bot chatidagi buyurtmalar bilan bir xil qoida.

## O'rnatish

Talab: **Node.js 22.13+** (ichki `node:sqlite` ishlatiladi — native modul kompilyatsiyasi kerak emas).
https://nodejs.org dan LTS versiyani o'rnating.

```powershell
cd $HOME\Desktop\magicslayd\web
npm install
npm run install:all
copy server\.env.example server\.env
```

`server\.env` da `BOT_DIR` bot papkasiga qarab turadi (standart: `../../bot`).
`BOT_TOKEN` va `ADMIN_ID` botning `.env` faylidan o'qiladi — qayta yozish shart emas.

> Bot yangi kod bilan **kamida bir marta ishga tushgan** bo'lishi kerak (jadvallar va sozlamalarni yaratadi).

## Ishga tushirish (lokal)

```powershell
# 1) bot
cd $HOME\Desktop\magicslayd\bot
python bot.py

# 2) ilova (yangi terminalda)
cd $HOME\Desktop\magicslayd\web
npm run dev
```

- Client: http://localhost:5173 (API so'rovlari serverga proxy qilinadi)
- Server: http://localhost:3001

**Brauzerda Telegram'siz sinash:** `server\.env` ga `DEV_USER_ID=<telegram ID'ingiz>` yozing.

**Telegram ichida sinash:** Mini App faqat `https` da ochiladi. Tunnel oching:

```powershell
cloudflared tunnel --url http://localhost:5173
# yoki: ngrok http 5173
```

Chiqqan `https://...` manzilni botning `.env` fayliga yozing va botni qayta ishga tushiring:

```
WEBAPP_URL=https://xxxx.trycloudflare.com
```

Bot chatdagi menyu tugmasini «📱 Ilova» ga almashtiradi.

## Production (server)

```bash
npm run build          # client/dist yaratiladi
NODE_ENV=production npm start   # server API + build qilingan ilovani bitta portda beradi
```

Nginx/Caddy orqali `https://app.sizning-domen.uz` → `localhost:3001` va botning `.env` iga
`WEBAPP_URL=https://app.sizning-domen.uz`.

To'liq serverga joylash (bot + web + HTTPS, bitta buyruq): `../LAUNCH.md`.

## Admin: ommabop materiallar

Botga faylni yuboring, so'ng o'sha faylga **reply** qilib yozing:

```
/ommabop kurs 36 Marketing asoslari kurs ishi
```

Turlari: `pres`, `referat`, `mustaqil`, `kurs`, `shablon`. Ro'yxat: `/ommabop`, o'chirish: `/ommabop_del 12`.
Foydalanuvchi ilovada ⬇️ ni bossa, fayl uning Telegram chatiga yuboriladi.

## API

Barcha so'rovlar: `Authorization: tma <initData>`

| Metod | Yo'l | Vazifa |
|---|---|---|
| GET | `/api/bootstrap` | user, balans, sozlamalar, faol buyurtma |
| GET | `/api/balance`, `/api/transactions`, `/api/stats` | hamyon va statistika |
| POST | `/api/topup` | bot chatiga to'ldirish xabarini yuborish |
| GET/PUT | `/api/title` | titul ma'lumotlari |
| POST | `/api/orders` | yangi buyurtma |
| GET | `/api/orders/:id` | buyurtma holati (`pending` → `working` → `done` / `failed`) |
| GET | `/api/materials?q=&kind=` | ommabop materiallar |
| POST | `/api/materials/:id/send`, `/api/materials/:id/bookmark` | chatga yuborish, saqlash |
| GET | `/api/saved`, `/api/search?q=` | saqlanganlar, qidiruv |
| POST | `/api/documents/:id/send` | o'z hujjatini chatga qayta yuborish |
| POST | `/api/ai/generate` | AI yordamchi: `{type, topic, subject, size, language}` → `202 {jobId, left}`; xato: `400 {error, field}`, limit: `429` |
| GET | `/api/ai/jobs/:id` | holat: `pending` / `working` / `done` (natija + fayl havolalari) / `failed` |
| GET | `/api/ai/limits` | kunlik bepul limit: `{limit, used, left}` |

## Hisob: telefon + parol

- Ilova **mehmon rejimida** ochiladi (ko'rish: bosh sahifa, dizaynlar, materiallar, qidiruv). Yaratish, like,
  saqlash, loyihalar, hamyon — hisob talab qiladi (`requireAccount` in `server/src/auth.js`, client: `push()` / `requireAuth()`).
- Hisob Telegram user'iga bog'lanadi (`accounts.user_id = users.id`) — balans va hujjatlar o'zgarmaydi.
- Ro'yxatdan o'tish: ilovada (Telegram ichida) yoki botda `/royxat` / «🔐 Hisobim» (kontakt orqali tasdiqlangan raqam).
- Kirish: raqam + parol → sessiya tokeni (`X-Session` sarlavhasi, 90 kun). Oddiy brauzerda ham ishlaydi.
- Parolni tiklash: raqam → 6 xonali kod **bot orqali Telegram chatga** (5 daqiqa, 5 urinish, 60 s qayta yuborish) → yangi parol.
  Botda `/parol` ham parolni yangilaydi. Parol o'zgarsa barcha sessiyalar yopiladi.
- Parol xeshi: scrypt (Node va Python bir xil format — `server/src/accounts.js`, `bot/accounts.py`).

| Metod | Yo'l | Vazifa |
|---|---|---|
| POST | `/api/auth/register` | `{phone, password}` → `{token, account}` (faqat Telegram ichida) |
| POST | `/api/auth/login`, `/api/auth/logout` | kirish / chiqish |
| POST | `/api/auth/reset/request` → `/reset/verify` → `/reset/confirm` | parolni tiklash |
| POST | `/api/auth/password` | `{current, password}` — parolni o'zgartirish |

## AI yordamchi

- **Promptlar:** `bot/assistant/prompts.py` (har ish turi uchun alohida, oson tahrirlanadi).
- **Sozlamalar** (botning `.env`): `ANTHROPIC_API_KEY` (majburiy), `AI_ASSISTANT_DAILY_LIMIT=3`,
  `AI_ASSISTANT_PER_MINUTE=2`, `AI_ASSISTANT_MODEL=claude-sonnet-5-5`. Saytga bot o'zi uzatadi.
- **Fayllar:** taqdimot → `.pptx`; referat / mustaqil ish / kurs ishi → `.docx` va `.pdf`
  (Times New Roman 14, interval 1.5, hoshiyalar 3 / 1.5 / 2 / 2 sm, titul, reja, sahifa raqamlari).
  PDF: LibreOffice bo'lsa Word'dan, bo'lmasa PyMuPDF bilan.
- **Pullik tarif qo'shish:** `assistant/service.py` → `daily_limit()` da userning tarifini tekshirish yetarli.
- **Javob uzun bo'lgani uchun** `POST /api/ai/generate` darhol `jobId` qaytaradi, ilova holatni so'rab turadi
  (proksi / Cloudflare'ning 100 soniyalik chegarasiga urilmaydi).

## Testlar

```powershell
cd server; npm test                                   # validatsiya, tozalash, limitlar
cd ..\..\bot; python -m unittest discover -s tests -v   # servis, limit, xatolar, Word/PDF/PPTX
```
