# MagicSlayd

Telegram bot **@MagicSlayd_bot** + Mini App (web ilova): taqdimot, referat, mustaqil ish, kurs ishi,
diplom, dissertatsiya va maqolalarni AI yordamida yaratadi.

```
magicslayd/
├── bot/                 ← Telegram bot (Python, aiogram). Sozlamalar: bot/.env (yagona manba)
├── web/                 ← Mini App: web/client (React + Vite), web/server (Node.js API)
├── data/                ← bot.db va loyihalar — bot va web umumiy ishlatadi (ZAXIRALANG!)
├── scripts/             ← tunnel.ps1 (lokal), serverga-yukla.ps1, server-setup.sh
├── docker-compose.yml   ← server: bot + web + HTTPS (Caddy) → https://magicslayd.uz
├── Caddyfile, .env      ← DOMAIN=magicslayd.uz
├── ishga-tushir.bat     ← kompyuterda ishga tushirish
├── toxtat.bat           ← kompyuterda to'xtatish
├── serverga-yukla.bat   ← birinchi marta serverga yuklash (baza bilan)
├── serverni-yangila.bat ← kod o'zgarganda serverni yangilash (baza saqlanadi)
└── LAUNCH.md            ← magicslayd.uz ga launch, qadamma-qadam
```

## Sozlamalar

Barcha kalitlar **bitta** faylda: `bot/.env` (namuna: `bot/.env.example`). Web server tokenni ham shu yerdan o'qiydi.
Serverda qo'shimcha faqat `.env` (`DOMAIN=...`).

## Kompyuterda ishga tushirish

Talab: Python 3.12+ (`pip install -r bot/requirements.txt`), Node.js 22.13+, cloudflared.

1. `ishga-tushir.bat` ni ikki marta bosing — bot, web server va tunnel ishga tushadi.
2. Telegram → @MagicSlayd_bot → `/start` → «Ilova».

Web ilovaning client qismi o'zgarsa: `cd web && npm run build`.

## Serverga joylash

[LAUNCH.md](LAUNCH.md) ga qarang.

## Testlar

```powershell
cd bot; python -m unittest discover -s tests
cd ..\web\server; npm test
```
