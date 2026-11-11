"""Slaydlar va hujjatlar uchun mavzuga mos rasmlarni topadi va yuklab oladi.
Manba: .env dagi kalitga qarab Pexels yoki Pixabay (professional fotolar), kalit bo'lmasa Wikimedia Commons.

Moslik: har bir topilgan rasmning teglari (Pixabay/Pexels) yoki nomi (Wikimedia) so'rov so'zlari bilan
solishtiriladi — eng mosi tanlanadi, umuman mos kelmaganlari tashlanadi. Slayd uchun mos rasm topilmasa,
butun mavzu bo'yicha qidiriladi, shunda rasm baribir mavzuga oid bo'ladi."""
import asyncio
import io
import logging
import re
import time

import aiohttp
from PIL import Image

import api_stats
from config import PEXELS_API_KEY, PIXABAY_API_KEY

USER_AGENT = "SlaydReferatBot/1.0 (https://t.me/slayd_referatai_bot)"
MAX_SIDE = 1600
SKIP_WORDS = ("logo", "icon", "flag", "coat of arms", "coat_of_arms", "signature", "seal", "emblem", "symbol", "map of")
# O'quvchilar uchun bot — Wikimedia'da (safesearch yo'q) bunday rasmlar hech qachon olinmaydi
UNSAFE_WORDS = ("nude", "naked", "nudity", "sex", "erotic", "porn", "topless", "lingerie", "breast", "genital",
                "corpse", "dead body", "gore", "execution", "autopsy", "torture")
# Slaydda professional ko'rinmaydigan rasmlar: yozuvli, fon/oboy, grafika — boshqa variant bo'lsa olinmaydi
WEAK_TAGS = {"text", "word", "words", "letter", "letters", "typography", "quote", "infographic", "wallpaper",
             "background", "backdrop", "template", "mockup", "banner", "clipart", "illustration", "pattern",
             "texture", "abstract", "font", "sign", "screenshot"}
STOP_WORDS = {"a", "an", "the", "of", "in", "on", "and", "with", "for", "at", "to", "from", "by", "or"}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)  # bitta so'rov
# Bir guruh rasmni qidirish uchun eng ko'p vaqt. Har bir ichki slaydga / bo'limga rasm qo'yilgani uchun
# 20 s yetmasdi (ulgurmagan rasmlar tashlanardi) — 45 s, buyurtma baribir rasm sababli juda cho'zilmaydi
BATCH_TIMEOUT = 60  # AI tekshiruvi bilan har bir nomzod ~1-2 s qo'shadi
# Barcha buyurtmalar uchun umumiy: bir vaqtda nechta rasm qidiriladi (foto bazalar limitiga urilmaslik uchun)
SEARCH_SLOTS = asyncio.Semaphore(8)
CACHE_TTL = 24 * 3600  # qidiruv natijalari 24 soat eslab qolinadi (tezlik; Pixabay qoidasi ham shuni so'raydi)

_cache = {}  # (manba, so'rov) -> (vaqt, [(url, matn), ...])


def ordered_words(text):
    """Solishtirish uchun so'zlar (tartibi saqlanadi): kichik harf, keraksiz so'zlarsiz, 5 harfgacha qisqartirilgan
    (panels/panel, students/student kabi shakllar bir xil hisoblansin)."""
    result = []
    for w in re.findall(r"[a-z]+", text.lower()):
        if w not in STOP_WORDS and len(w) > 2 and w[:5] not in result:
            result.append(w[:5])
    return result


def words(text):
    return set(ordered_words(text))


# Davr yoki uslubni bildiruvchi umumiy so'zlar (5 harfgacha) — rasmda «asosiy predmet» bo'la olmaydi:
# «medieval horse archers» so'rovida asosiy predmet «horse», «medieval» emas
GENERIC = {"medie", "ancie", "histo", "old", "tradi", "moder", "vinta", "class", "famou", "beaut", "antiq", "retro"}


def main_index(wanted):
    """Asosiy predmet — birinchi umumiy bo'lmagan so'z."""
    return next((i for i, w in enumerate(wanted) if w not in GENERIC), 0)


def relevance(query, description, loose=False):
    """Rasm so'rovga qanchalik mos (0 — mos emas, rad etiladi).
    Shartlar: birinchi so'z (eng muhim predmet — Claude'dan shunday so'raladi: «Timurid», «Samarkand», «teacher»)
    albatta bo'lishi va kamida 2 ta so'z mos kelishi. Aks holda «Timurid army cavalry» so'roviga
    «army» va «cavalry» mos keladigan Yevropa ritsarlari rasmi tushib qolardi — noto'g'ri rasmdan rasmsiz yaxshi.
    loose=True — faqat asosiy predmet yetarli: bunday nomzodlarni keyin AI ko'zi (check) rasmning o'ziga qarab tekshiradi."""
    wanted, have = ordered_words(query), words(description)
    hits = [w in have for w in wanted]
    matched = sum(hits)
    if not wanted or not hits[main_index(wanted)] or (not loose and matched < min(2, len(wanted))):
        return 0
    return matched + 1


def weak(description):
    """Yozuvli, fon (wallpaper) yoki grafik rasm — boshqa variant bo'lsa tanlanmaydi."""
    return bool(set(re.findall(r"[a-z]+", description.lower())) & WEAK_TAGS)


def track_limits(service, response):
    """Admin panel uchun: so'rovlar soni, xatolar va manba qaytargan limit sarlavhalari
    (Pixabay/Pexels: X-RateLimit-Limit / -Remaining / -Reset)."""
    api_stats.bump(service)
    if response.status != 200:
        api_stats.bump(service, "errors")
    headers = response.headers
    remaining = headers.get("X-RateLimit-Remaining") or headers.get("X-Ratelimit-Remaining")
    limit = headers.get("X-RateLimit-Limit") or headers.get("X-Ratelimit-Limit")
    reset = headers.get("X-RateLimit-Reset") or headers.get("X-Ratelimit-Reset")
    state = {"last_status": response.status}
    if remaining is not None and str(remaining).isdigit():
        state.update(remaining=int(remaining), limit=int(limit) if str(limit or "").isdigit() else None,
                     reset_seconds=int(reset) if str(reset or "").isdigit() else None)
    if response.status == 429:
        state["rate_limited_at"] = time.strftime("%Y-%m-%d %H:%M")
    elif response.status in (401, 403):
        state["error"] = "Kalit noto'g'ri yoki bloklangan"
    elif response.status == 200:
        state["error"] = None
    api_stats.set_state(service, **state)


# ===== Manbalar: har biri [(url, tavsif), ...] qaytaradi =====
async def pexels_search(session, query):
    params = {"query": query, "per_page": 15, "orientation": "landscape"}
    async with session.get("https://api.pexels.com/v1/search", params=params,
                           headers={"Authorization": PEXELS_API_KEY}) as response:
        track_limits("pexels", response)
        if response.status != 200:
            logging.warning("Pexels %s: %s", response.status, query)
            return []
        data = await response.json()
    return [(p["src"]["large2x"], f"{p.get('alt', '')} {p.get('url', '')}") for p in data.get("photos", [])]


async def pixabay_search(session, query):
    params = {
        "key": PIXABAY_API_KEY, "q": query[:100], "image_type": "photo", "orientation": "horizontal",
        "safesearch": "true", "per_page": 20, "min_width": 1000,
    }
    async with session.get("https://pixabay.com/api/", params=params) as response:
        track_limits("pixabay", response)
        if response.status != 200:
            logging.warning("Pixabay %s: %s", response.status, query)
            return []
        data = await response.json()
    return [(hit["largeImageURL"], hit.get("tags", "")) for hit in data.get("hits", [])]


async def wikimedia_search(session, query):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 15,
        "gsrsearch": f"{query} filetype:bitmap", "prop": "imageinfo", "iiprop": "url|size|mime", "iiurlwidth": MAX_SIDE,
    }
    async with session.get("https://commons.wikimedia.org/w/api.php", params=params) as response:
        track_limits("wikimedia", response)
        if response.status != 200:
            return []
        data = await response.json()
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    results = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        width, height = info.get("width", 0), info.get("height", 1)
        title = page.get("title", "").replace("_", " ")
        if (info.get("mime") in ("image/jpeg", "image/png") and width >= 900 and 0.6 <= width / height <= 2.2
                and not any(word in title.lower() for word in SKIP_WORDS + UNSAFE_WORDS)):
            results.append((info.get("thumburl") or info.get("url"), title))
    return results


def source():
    if PEXELS_API_KEY:
        return "pexels", pexels_search
    if PIXABAY_API_KEY:
        return "pixabay", pixabay_search
    return "wikimedia", wikimedia_search


def sources():
    """Qidiruv tartibi: kaliti bor HAMMA stok manbalar (Pexels, keyin Pixabay), keyin Wikimedia — tarixiy joylar,
    shaxslar va O'zbekistonga xos mavzular (Registon, Amir Temur...) stok saytlarda bo'lmasa ham Wikimedia'da bor.
    Bitta manbada mos rasm bo'lmasa — keyingisida qidiriladi, shuning uchun rasmlar ko'proq va mosroq topiladi."""
    chain = []
    if PEXELS_API_KEY:
        chain.append(("pexels", pexels_search))
    if PIXABAY_API_KEY:
        chain.append(("pixabay", pixabay_search))
    return chain + [("wikimedia", wikimedia_search)]


async def search(session, query, chosen=None):
    """Qidiruv natijalari (keshdan yoki manbadan). chosen — (nom, funksiya); berilmasa asosiy manba."""
    name, function = chosen or source()
    key = (name, query.lower())
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    try:
        results = await function(session, query)
    except Exception:
        logging.warning("Rasm qidiruvida xato: %s", query)
        return []
    _cache[key] = (time.time(), results)
    if len(_cache) > 2000:  # xotira to'lib ketmasin — eng eskilarini tashlaymiz
        for old in sorted(_cache, key=lambda k: _cache[k][0])[:500]:
            _cache.pop(old, None)
    return results


# ===== Yuklab olish =====
def trim_bars(image):
    """Tepa/pastdagi (yoki yon tomondagi) qora «kino chiziqlari»ni kesadi — AI ba'zan shunday chizadi."""
    gray = image.convert("L")
    width, height = gray.size
    pixels = gray.load()

    def dark_row(y):
        return max(pixels[x, y] for x in range(0, width, 8)) < 24

    def dark_col(x):
        return max(pixels[x, y] for y in range(0, height, 8)) < 24

    top = next((y for y in range(height // 3) if not dark_row(y)), 0)
    bottom = next((y for y in range(height - 1, height - height // 3, -1) if not dark_row(y)), height - 1) + 1
    left = next((x for x in range(width // 3) if not dark_col(x)), 0)
    right = next((x for x in range(width - 1, width - width // 3, -1) if not dark_col(x)), width - 1) + 1
    def symmetric(a, b, size):
        # Haqiqiy chiziqlar ikkala tomonda deyarli bir xil; bir tomonda qorong'i bo'lsa (tungi osmon) — bu surat qismi
        return min(a, b) >= size * 0.02 and abs(a - b) <= max(a, b) * 0.35
    if not symmetric(top, height - bottom, height):
        top, bottom = 0, height
    if not symmetric(left, width - right, width):
        left, right = 0, width
    if (top, bottom, left, right) == (0, height, 0, width):
        return image
    if (bottom - top) < height * 0.6 or (right - left) < width * 0.6:
        return image  # ataylab qorong'i surat — tegmaymiz
    return image.crop((left, top, right, bottom))


def normalize(data):
    """Rasmni tekshiradi, RGB ga o'tkazadi, kichraytiradi va JPEG qiladi (fayl hajmi kichik bo'lishi uchun)."""
    image = Image.open(io.BytesIO(data))
    image.load()
    image = trim_bars(image.convert("RGB"))
    if image.width < 600 or image.height < 400 or not 0.6 <= image.width / image.height <= 2.5:
        return None
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=82, optimize=True)
    return buffer.getvalue()


async def download(session, url):
    try:
        async with session.get(url) as response:
            if response.status != 200:
                return None
            data = await response.read()
        return await asyncio.to_thread(normalize, data)
    except Exception:
        logging.warning("Rasm yuklanmadi: %s", url)
        return None


def variants(query):
    """So'rov va uning qisqarishlari: oxiridan bittadan so'z olib tashlanadi, kamida 2 so'z qoladi
    («teacher grading papers desk» → «teacher grading papers» → «teacher grading»). Asosiy predmet saqlanadi."""
    parts = (query or "").split()
    return [" ".join(parts[:n]) for n in range(len(parts), 1, -1)] or ([query] if query else [])


def fingerprint(data):
    """Rasmning 64 bitli perseptual xeshi (dHash): bir xil surat boshqa o'lcham yoki manzilda ham bir xil chiqadi."""
    with Image.open(io.BytesIO(data)) as image:
        small = list(image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = bits << 1 | (small[row * 9 + col] > small[row * 9 + col + 1])
    return bits


def duplicate(mark, used):
    """Taqdimotda allaqachon bor suratmi (xeshlar deyarli bir xil). used ichida xeshlar ("h", son) ko'rinishida."""
    return any(isinstance(item, tuple) and bin(item[1] ^ mark).count("1") <= 8 for item in list(used))


# AI ko'zi bilan tekshiruv (check) bo'lsa: bitta slayd uchun eng ko'p shuncha nomzod ko'rsatiladi — qolgani
# AI illyustratsiya bilan to'ldiriladi (vaqt va pul cheksiz ketmasin; bitta tekshiruv ~0.0001 $)
MAX_CHECKS = 6


class Checker:
    """Bitta slayd uchun AI tekshiruvi: check(image) → True (mos) / False (mos emas) / None (tekshirib bo'lmadi)."""

    def __init__(self, check):
        self.check, self.left = check, MAX_CHECKS

    async def accepts(self, image, strict):
        if self.check is None:
            return strict
        if self.left <= 0:
            return False
        self.left -= 1
        try:
            verdict = await self.check(image)
        except Exception:
            logging.warning("Rasmni AI bilan tekshirib bo'lmadi", exc_info=True)
            verdict = None
        # Tekshirib bo'lmasa — foto olinmaydi: teglar ko'pincha yolg'on (masalan «marketing» tegli siyosatchi surati).
        # Noto'g'ri rasmdan ko'ra slayd mazmuni bo'yicha AI chizgan rasm yaxshi (chaqiruvchi o'zi to'ldiradi)
        return bool(verdict)


async def try_variant(session, variant, chosen, used, checker=None):
    checker = checker or Checker(None)
    loose = checker.check is not None
    scored = []
    for i, (url, description) in enumerate(await search(session, variant, chosen)):
        if any(word in description.lower() for word in UNSAFE_WORDS):
            continue
        strict = relevance(variant, description)
        score = strict or (relevance(variant, description, loose=True) if loose else 0)
        if score:
            scored.append((not strict, weak(description), -score, i, url, bool(strict)))
    # Tartib: teglari qat'iy mos → oddiy fotolar yozuvli/fon rasmlardan oldin → eng mosi → mashhurrog'i
    for *_, url, strict in sorted(scored):
        if checker.check is not None and checker.left <= 0:
            return None
        if url in used:
            continue
        used.add(url)
        image = await download(session, url)
        if image:
            mark = await asyncio.to_thread(fingerprint, image)
            if duplicate(mark, used):
                continue  # boshqa manzildan kelgan, lekin taqdimotda allaqachon bor surat
            if not await checker.accepts(image, strict):
                continue  # rasm slayd mavzusiga mos emas (AI ko'rib chiqdi)
            used.add(("h", mark))
            return image
    return None


async def find_image(session, query, used, fallback=None, check=None):
    """Eng mos va hali ishlatilmagan rasmni qaytaradi (topilmasa None).
    Tartib: slayd so'rovi (to'liq, keyin qisqarishlari) — avval asosiy manbada, keyin Wikimedia'da;
    shunda ham topilmasa — butun mavzu bo'yicha (fallback) asosiy manbada.
    check — rasmni AI bilan tekshiruvchi funksiya (bo'lsa, faqat u «mos» degan rasm olinadi)."""
    steps = [(variant, chosen) for chosen in sources() for variant in variants(query)]
    if fallback:
        steps += [(variant, source()) for variant in variants(fallback)]
    checker = Checker(check)
    seen = set()
    for variant, chosen in steps:
        if (variant.lower(), chosen[0]) in seen:
            continue
        seen.add((variant.lower(), chosen[0]))
        image = await try_variant(session, variant, chosen, used, checker)
        if image:
            return image
        if check is not None and checker.left <= 0:
            break
    return None


async def find_images(queries, used=None, fallback=None, checks=None):
    """Har bir so'rov uchun bitta rasm (topilmasa None). Rasmlar takrorlanmaydi (used — ishlatilgan URL'lar).
    fallback — mavzu bo'yicha so'rov: slayd uchun mos rasm bo'lmasa shu bilan qidiriladi.
    checks — har bir so'rov uchun AI tekshiruv funksiyasi (yoki None): rasmning o'ziga qarab mosligini aniqlaydi.
    Hech qachon xato tashlamaydi va BATCH_TIMEOUT dan uzoq kuttirmaydi."""
    used = set() if used is None else used
    checks = list(checks or [])
    checks += [None] * (len(queries) - len(checks))

    async def one(session, query, check):
        async with SEARCH_SLOTS:
            return await find_image(session, query, used, fallback, check) if query else None

    if not queries:
        return []
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT) as session:
            tasks = [asyncio.create_task(one(session, q, c)) for q, c in zip(queries, checks)]
            done, pending = await asyncio.wait(tasks, timeout=BATCH_TIMEOUT)
            if pending:  # ulgurmaganlari bekor qilinadi, topilganlari saqlanadi
                logging.warning("Rasm qidiruvi vaqti tugadi: %s ta rasm ulgurmadi", len(pending))
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            return [task.result() if task in done and not task.exception() else None for task in tasks]
    except Exception:
        logging.exception("Rasmlarni qidirishda xato")
        return [None] * len(queries)


def spread(total, count, skip=()):
    """0..total-1 oralig'idan count ta indeksni teng taqsimlab tanlaydi (skip dagilardan tashqari)."""
    pool = [i for i in range(total) if i not in skip]
    count = min(count, len(pool))
    return [pool[int((i + 0.5) * len(pool) / count)] for i in range(count)] if count else []
