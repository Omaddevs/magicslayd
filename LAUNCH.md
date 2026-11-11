# MagicSlayd — magicslayd.uz ga launch

Natija: bot **@MagicSlayd_bot** va web ilova **https://magicslayd.uz** 24/7 ishlaydi, kompyuter kerak emas.
HTTPS sertifikat avtomatik (Caddy + Let's Encrypt). Domen `.env` da allaqachon yozilgan: `DOMAIN=magicslayd.uz`.

## 1-qadam. VPS sotib olish

- Ubuntu **24.04**, kamida **2 GB RAM**, 20 GB disk.
  Masalan: Hetzner CX22 (~5 $/oy), Ahost.uz / Timeweb (O'zbekistonga yaqin, tezroq).
- Natijada sizga beriladi: **IP manzil** (masalan `65.21.10.20`) va **root paroli**.

## 2-qadam. Domenni serverga ulash (DNS)

Domen sotib olingan joyda (masalan cctld.uz ro'yxatdagi registrator: Ahost, Webspace, Billur ...)
DNS boshqaruviga kiring va ikkita yozuv qo'shing:

| Turi | Nomi (Host) | Qiymati | TTL |
|---|---|---|---|
| A | `@` | SERVER_IP | 3600 |
| A | `www` | SERVER_IP | 3600 |

Tekshirish (kompyuterda, PowerShell): `Resolve-DnsName magicslayd.uz` → server IP chiqishi kerak.
`.uz` domenlarda DNS 15 daqiqadan bir necha soatgacha yangilanadi.

## 3-qadam. Kalitlarni yangilash

`bot\.env` ni Notepad'da oching va yangi kalitlarni yozing (chatga yubormang):
- `ANTHROPIC_API_KEY` — platform.claude.com → API Keys
- `PIXABAY_API_KEY` — pixabay.com/api/docs → Rotate
- `CLOUDFLARE_API_TOKEN` — dash.cloudflare.com → API Tokens → Roll
- `PAYMENT_CARDS`, `ADMIN_ID` — to'g'riligini tekshiring

## 4-qadam. Serverga yuklash (bitta tugma)

`magicslayd\serverga-yukla.bat` ni ikki marta bosing → server IP ni kiriting → parol so'ralganda root parolini kiriting
(2 marta so'raladi; yozganda ko'rinmaydi — bu normal). Skript o'zi:

1. kompyuterdagi bot va tunnelni to'xtatadi (bitta token bilan ikkita bot ishlamaydi);
2. kod, `bot/.env` va **baza** (`data/` — userlar, balanslar) ni arxivlab serverga yuklaydi;
3. serverda Docker o'rnatadi, bot + web + HTTPS ni ishga tushiradi, kunlik zaxirani yoqadi.

Birinchi marta 5–10 daqiqa. Oxirida «Tayyor! https://magicslayd.uz» chiqadi.

> SSH birinchi marta ulanganda `Are you sure you want to continue connecting?` desa — `yes` yozing.

## 5-qadam. Tekshirish

- [ ] https://magicslayd.uz/api/health → `{"ok":true}`
- [ ] https://magicslayd.uz → sayt ochiladi (qulf belgisi bor)
- [ ] Telegram → @MagicSlayd_bot → `/start` → **«Ilova»** → ilova ochiladi
- [ ] 5 slaydli taqdimot buyurtma qilish → fayl keladi
- [ ] Hisobni to'ldirish → admin chatiga chek keladi

## 6-qadam. BotFather sozlamalari

@BotFather → `/mybots` → @MagicSlayd_bot:
- **Bot Settings → Configure Mini App → Enable** → URL: `https://magicslayd.uz`
- **Bot Settings → Menu Button** — bot o'zi «Ilova» qilib qo'yadi, tegmang
- `Edit Bot` → rasm (`/setuserpic`), tavsif (`/setdescription`), qisqa matn (`/setabouttext`)

## Kod o'zgarganda

`serverni-yangila.bat` → server IP. Serverdagi baza va balanslar **saqlanadi** (`data/` va `.env` yuborilmaydi).

## Serverda kundalik ishlar

`ssh root@SERVER_IP`, keyin `cd /opt/magicslayd`:

| Nima | Buyruq |
|---|---|
| Loglar | `docker compose logs -f --tail 100` (chiqish: Ctrl+C) |
| Faqat bot logi | `docker compose logs -f bot` |
| Qayta ishga tushirish | `docker compose restart` |
| To'xtatish | `docker compose down` |
| Holat | `docker compose ps` |
| Zaxiralar | `ls /root/backups` (har kuni 04:00, 14 kun saqlanadi) |
| Zaxirani kompyuterga olish | kompyuterda: `scp root@SERVER_IP:/root/backups/bot-2026-11-10.db .` |

## Muammolar

| Belgisi | Sabab va yechim |
|---|---|
| Sayt ochilmaydi, «sertifikat xatosi» | DNS hali server IP'ga qaramagan. `Resolve-DnsName magicslayd.uz` bilan tekshiring; to'g'ri bo'lgach Caddy sertifikatni o'zi oladi (`docker compose logs caddy`) |
| `TelegramConflictError` logda | Bot boshqa joyda ham ishlayapti — kompyuterda `toxtat.bat` |
| Bot javob bermaydi | `docker compose logs --tail 50 bot` — xatoni o'qing |
| «Ilova» tugmasi eski manzilni ochadi | Telegram'da botni qayta oching yoki `/start` |

## Bilish kerak

- Baza WAL rejimida — ishlab turganda `cp bot.db` qilmang, zaxira `sqlite3 .backup` bilan olinadi (avtomatik).
- Taqdimot loyihalari `data/decks/` da **60 kun** saqlanadi (fayl Telegram'da qoladi).
- Token almashgani uchun eski bot yuborgan fayllarni yangi bot qayta yubora olmaydi (`file_id` har botga alohida).
