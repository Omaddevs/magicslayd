"""Shablon uslubidagi rasmlarni AI bilan generatsiya qiladi.

Har bir rasm slayd mavzusi va shablon uslubi (themes.py → image_style) bo'yicha chiziladi: Korporativ — ofis
fotosi, Daftar — qo'lda chizilgan illyustratsiya, Tarix — sepiya arxiv foto, Barokko — moyli rasm.

Xizmat (.env dagi kalitga qarab): Google Gemini (pullik, eng sifatli) yoki Cloudflare Workers AI — FLUX-1 schnell
(BEPUL: kuniga ~10 000 «neyron»). Ikkalasi ham bo'lsa — Gemini, u ishlamasa Cloudflare.
Gemini: avval Interactions API, u ishlamasa eski generateContent; javobdagi rasm ikkala formatdan ham topiladi.
Hech qachon xato tashlamaydi: chizib bo'lmagan rasm o'rniga None qaytadi — chaqiruvchi (presentation/ai.py)
uni foto qidiruvi bilan to'ldiradi."""
import asyncio
import base64
import logging
import time
from datetime import datetime, timedelta, timezone

import aiohttp

import api_stats
from config import (
    CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, GEMINI_API_KEY, GEMINI_CONCURRENCY, GEMINI_IMAGE_MODEL,
)
from presentation.images import normalize

API = "https://generativelanguage.googleapis.com/v1beta"
API_REVISION = "2026-05-20"
CF_API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell"
CF_STEPS = 6  # 4–8: ko'proq — sifatliroq, lekin bepul limitdan ko'proq yeydi (~130 rasm/kun)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10)  # bitta rasm
BATCH_TIMEOUT = 75  # bir guruh rasm uchun eng ko'p kutish — buyurtma rasm sababli cho'zilib ketmasin
SLOTS = asyncio.Semaphore(GEMINI_CONCURRENCY)  # barcha buyurtmalar uchun umumiy

_legacy_only = False  # Interactions API bu kalit/model uchun ishlamasa — keyingi so'rovlar to'g'ridan-to'g'ri eskisiga
_disabled_until = 0.0  # Gemini kaliti noto'g'ri yoki limit tugagan bo'lsa — bir muddat urinilmaydi
_cf_disabled_until = 0.0  # Cloudflare: bepul kunlik limit tugasa — ertasi kun (UTC) gacha


def gemini_ready():
    return bool(GEMINI_API_KEY) and time.monotonic() >= _disabled_until


def cloudflare_ready():
    return bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN) and time.monotonic() >= _cf_disabled_until


def enabled():
    return gemini_ready() or cloudflare_ready()


def prompt_for(scene, context, topic, style):
    """scene — Claude yozgan sahna tavsifi (ingliz tilida, tarixiy va madaniy tafsilotlar bilan)."""
    return (
        f"Create an illustration for a presentation slide. Scene: {scene}\n"
        f"Slide title: «{context}». Presentation topic: «{topic}».\n"
        f"Art style: {style}.\n"
        "Requirements: historically and culturally accurate for this topic — correct era, region, people's appearance, "
        "clothing, armor, weapons, architecture and landscape; do not substitute another culture or era "
        "(for example, no European knights or Western castles for a Central Asian topic). "
        "Wide 16:9 landscape composition, the main subject clearly visible and well lit, dignified and suitable "
        "for students. Absolutely no text, letters, numbers, captions, logos, UI elements or watermarks."
    )


def find_image(node):
    """Javobdan base64 rasmni topadi (Interactions: steps/output_image/content bloklari;
    generateContent: candidates/content/parts/inlineData). Topilmasa — None."""
    if isinstance(node, dict):
        inline = node.get("inlineData") or node.get("inline_data")
        if isinstance(inline, dict) and isinstance(inline.get("data"), str):
            return inline["data"]
        mime = str(node.get("mime_type") or node.get("mimeType") or "")
        data = node.get("data")
        if isinstance(data, str) and len(data) > 1000 and (mime.startswith("image/") or node.get("type") == "image"):
            return data
        for value in node.values():
            found = find_image(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_image(value)
            if found:
                return found
    return None


async def _post(session, url, body, headers=None):
    async with session.post(url, json=body, headers={"x-goog-api-key": GEMINI_API_KEY, **(headers or {})}) as response:
        payload = await response.json(content_type=None)
        return response.status, payload


async def _interactions(session, prompt):
    body = {
        "model": GEMINI_IMAGE_MODEL,
        "input": [{"type": "text", "text": prompt}],
        "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": "16:9", "image_size": "1K"},
    }
    return await _post(session, f"{API}/interactions", body, {"Api-Revision": API_REVISION})


async def _generate_content(session, prompt):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}},
    }
    return await _post(session, f"{API}/models/{GEMINI_IMAGE_MODEL}:generateContent", body)


async def cloudflare_one(session, prompt):
    """Cloudflare Workers AI (FLUX-1 schnell) — bepul. Javob: {"result": {"image": base64}, "success": true}."""
    global _cf_disabled_until
    url = CF_API.format(account=CLOUDFLARE_ACCOUNT_ID)
    body = {"prompt": prompt[:2048], "steps": CF_STEPS}
    headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    for attempt in range(2):
        try:
            async with session.post(url, json=body, headers=headers) as response:
                status, payload = response.status, await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            logging.warning("Cloudflare rasm so'rovi xatosi: %s", e)
            await asyncio.sleep(2)
            continue
        data = ((payload or {}).get("result") or {}).get("image") if isinstance(payload, dict) else None
        if status == 200 and data:
            api_stats.bump("cloudflare", "images")
            api_stats.set_state("cloudflare", limit_until=None, error=None)
            return await asyncio.to_thread(normalize, base64.b64decode(data))
        api_stats.bump("cloudflare", "errors")
        message = str((payload or {}).get("errors", payload))[:300] if isinstance(payload, dict) else str(payload)[:300]
        if status in (401, 403):
            logging.error("Cloudflare token yoki Account ID noto'g'ri (Workers AI ruxsati kerak): %s", message)
            api_stats.set_state("cloudflare", error="Token yoki Account ID noto'g'ri")
            _cf_disabled_until = time.monotonic() + 600
            return None
        if status == 429 or "4006" in message:  # kunlik bepul limit tugadi — ertasi kun 00:00 UTC da tiklanadi
            now = datetime.now(timezone.utc)
            reset = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), timezone.utc)
            logging.warning("Cloudflare bepul limiti tugadi — rasmlar fotobazadan olinadi: %s", message)
            api_stats.set_state("cloudflare", limit_until=reset.isoformat(timespec="minutes"))
            _cf_disabled_until = time.monotonic() + (reset - now).total_seconds()
            return None
        if status >= 500:
            await asyncio.sleep(2 + attempt * 3)
            continue
        logging.warning("Cloudflare rasm chizmadi %s: %s", status, message)
        return None
    return None


async def generate_one(session, prompt):
    """Avval Gemini (kaliti bo'lsa), u chiza olmasa — Cloudflare."""
    image = await gemini_one(session, prompt) if gemini_ready() else None
    if image is None and cloudflare_ready():
        image = await cloudflare_one(session, prompt)
    return image


async def gemini_one(session, prompt):
    global _legacy_only, _disabled_until
    for attempt in range(2):
        for call in [_generate_content] if _legacy_only else [_interactions, _generate_content]:
            try:
                status, payload = await call(session, prompt)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                logging.warning("Gemini rasm so'rovi xatosi (%s): %s", call.__name__, e)
                continue
            if status == 200:
                data = find_image(payload)
                if data:
                    image = await asyncio.to_thread(normalize, base64.b64decode(data))
                    if image:
                        api_stats.bump("gemini", "images")
                        api_stats.set_state("gemini", error=None)
                        return image
                logging.warning("Gemini rasm qaytarmadi (ehtimol xavfsizlik filtri): %s", str(payload)[:300])
                return None
            message = str((payload or {}).get("error", payload))[:300] if isinstance(payload, dict) else str(payload)[:300]
            api_stats.bump("gemini", "errors")
            if status in (401, 403):
                logging.error("Gemini kaliti noto'g'ri yoki ruxsat yo'q: %s", message)
                api_stats.set_state("gemini", error="Kalit noto'g'ri yoki ruxsat yo'q")
                _disabled_until = time.monotonic() + 600
                return None
            if status in (400, 404) and call is _interactions:
                logging.warning("Gemini Interactions API ishlamadi (%s), generateContent ishlatiladi: %s", status, message)
                _legacy_only = True
                continue
            if status == 429 or status >= 500:
                logging.warning("Gemini band (%s): %s", status, message)
                break  # biroz kutib qayta urinamiz
            logging.warning("Gemini xatosi %s: %s", status, message)
            return None
        await asyncio.sleep(2 + attempt * 3)
    return None


async def generate_images(prompts):
    """Har bir tavsif uchun rasm (JPEG bytes) yoki None. Hech qachon xato tashlamaydi."""
    if not prompts:
        return []
    if not enabled():
        return [None] * len(prompts)

    async def one(session, prompt):
        async with SLOTS:
            return await generate_one(session, prompt)

    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            tasks = [asyncio.create_task(one(session, p)) for p in prompts]
            done, pending = await asyncio.wait(tasks, timeout=BATCH_TIMEOUT)
            if pending:
                logging.warning("Rasm generatsiyasi vaqti tugadi: %s ta rasm ulgurmadi", len(pending))
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            return [task.result() if task in done and not task.exception() else None for task in tasks]
    except Exception:
        logging.exception("Rasmlarni generatsiya qilishda xato")
        return [None] * len(prompts)
