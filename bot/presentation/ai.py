"""Taqdimot matnini Claude AI orqali yozdiradi.
Tezlik uchun: avval qisqa reja (sarlavhalar) tuziladi, keyin slaydlar 3 tadan bo'laklarga bo'linib bir vaqtda
yoziladi, rasmlar esa har bir bo'lak tayyor bo'lishi bilan darhol qidiriladi."""
import asyncio
import base64
import io
import json
import logging
from contextlib import contextmanager

import anthropic
from PIL import Image

import ai_usage
import api_stats
from config import AI_MODEL, AI_MODEL_WRITER, API_CONCURRENCY, FIXED_SLIDES
from database import now_str
from presentation import genimage
from presentation.images import find_images, spread
from presentation.themes import THEMES

LANGUAGES = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
LANGUAGE_PROMPT = {
    "uz": "Uzbek (Latin script, modern literary Uzbek; use the oʻ and gʻ letters correctly)",
    "ru": "Russian",
    "en": "English",
}
KINDS = ("bullets", "cards", "stats", "timeline", "quote")
# Har bir maket uchun elementlar soni (min, max)
ITEM_LIMITS = {"bullets": (3, 6), "cards": (2, 4), "stats": (2, 4), "timeline": (3, 5), "quote": (0, 1)}
CHUNK = 3  # bitta so'rovda nechta slayd yoziladi (kichik bo'lak — tezroq)
# Bir vaqtda Claude'ga ketadigan so'rovlar chegarasi (barcha buyurtmalar uchun umumiy, .env: API_CONCURRENCY).
# Hisobning «concurrent requests» limiti: ~21 ta o'tdi, ~35 tasi 429 qaytardi (o'lchangan).
API_SLOTS = asyncio.Semaphore(API_CONCURRENCY)

OUTLINE_SYSTEM = """You plan presentations that students and teachers present in class.
Give only the structure: concise slide titles (at most 7 words), no slide texts. No markdown, no emoji, no numbering.
Choose a layout `kind` for every slide and vary them so the presentation looks lively:
"bullets" and "cards" are the most common; "stats" only where widely known, verifiable figures exist;
"timeline" for stages, steps or history; "quote" at most once in the whole presentation.
Slide titles inside a plan item must not overlap — each covers a different aspect.
Follow the exact number of plan items and slides per plan item that the user asks for."""

SLIDES_SYSTEM = """You write content for presentation slides that students and teachers present in class.
Every slide must be concise, factually accurate, and readable on a projector. No markdown, no emoji, no numbering.

How to fill each slide kind:
- "bullets": `text` is an optional one-sentence intro (may be empty). `items` are 3-5 points; `heading` is 1-3 words (or empty), `text` is at most 20 words.
- "cards": `text` optional intro. `items` are 3 cards (4 at most): `heading` 1-4 words, `text` at most 25 words.
- "stats": `items` are 3 widely known, verifiable facts: `heading` is the short figure ("1991", "75%", "8 mln"), `text` explains it in at most 12 words.
- "timeline": `items` are 3-5 steps in order: `heading` 1-4 words (a date or step name), `text` at most 15 words.
- "quote": `text` is a famous real quotation or a key idea, at most 30 words. `items` has one element whose `heading` is the author (empty if it is not a quotation).

`image_query`: 2-4 ENGLISH words for searching a real stock photo that illustrates the slide.
The FIRST word is the most distinctive subject that a matching photo must contain; then details:
"teacher grading papers", "solar panels on roof", "Registan Samarkand", "Timurid mausoleum Samarkand".
Concrete objects, people, places or scenes — never abstract ideas, charts or text.
For famous places, people or events use their real names. For history, culture or a specific country, the FIRST word
must be the region, culture or era anchor ("Timurid cavalry", "Samarkand madrasa", "Uzbek dancers", "Ottoman janissary",
"Egyptian pyramids") — never start with a generic word like medieval, ancient, historical, old, traditional or vintage.
A photo from another culture or era (e.g. European knights for a Central Asian topic) is worse than no photo.

`image_prompt`: ONE English sentence (25-45 words) for an AI image generator that paints an illustration for the slide:
the concrete scene (who or what, doing what, where), and the faithful historical and cultural details of the topic —
era, region, people's appearance and ethnicity, clothing, armor, tools, architecture, landscape, lighting.
Be accurate to the real context: Amir Temur → 14th-century Timurid Turco-Mongol warriors in lamellar armor and
pointed helmets, Central Asian steppe, Samarkand with blue-tiled domes; never generic European or fantasy imagery.
Modern topics → modern, realistic settings in the relevant country. No text, letters, maps with labels or charts."""

_ITEMS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"heading": {"type": "string"}, "text": {"type": "string"}},
        "required": ["heading", "text"],
        "additionalProperties": False,
    },
}
PLANS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "image_query": {"type": "string"},
        "image_prompt": {"type": "string"},
        "plans": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "subtitle", "image_query", "image_prompt", "plans"],
    "additionalProperties": False,
}
SLIDE_TITLES_SCHEMA = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "kind": {"type": "string", "enum": list(KINDS)}},
                "required": ["title", "kind"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["slides"],
    "additionalProperties": False,
}
CHUNK_SCHEMA = {
    "type": "object",
    "properties": {
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "image_query": {"type": "string"},
                               "image_prompt": {"type": "string"}, "items": _ITEMS},
                "required": ["text", "image_query", "image_prompt", "items"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["slides"],
    "additionalProperties": False,
}
CONCLUSION_SCHEMA = {
    "type": "object",
    "properties": {"conclusion": {"type": "array", "items": {"type": "string"}}},
    "required": ["conclusion"],
    "additionalProperties": False,
}


class GenerationError(Exception):
    """Foydalanuvchiga ko'rsatsa bo'ladigan xato. admin_alert — adminga ham yuboriladigan matn (bo'lsa)."""

    def __init__(self, message, admin_alert=None):
        super().__init__(message)
        self.admin_alert = admin_alert


_client = None


def client():
    global _client
    if _client is None:
        # kalit ANTHROPIC_API_KEY dan o'qiladi; 429 bo'lsa SDK qisqa qayta urinadi, keyin ask_json kutib turadi
        _client = anthropic.AsyncAnthropic(max_retries=2)
    return _client


@contextmanager
def api_errors():
    """Claude API xatolarini foydalanuvchiga ko'rsatsa bo'ladigan GenerationError ga aylantiradi."""
    try:
        yield
    except (anthropic.AuthenticationError, TypeError):
        # TypeError — SDK hech qanday kalit topa olmaganda (.env da ANTHROPIC_API_KEY yo'q)
        logging.exception("Claude API kaliti yo'q yoki noto'g'ri")
        api_stats.set_state("claude", error="API kaliti yo'q yoki noto'g'ri", error_at=now_str())
        raise GenerationError("AI xizmati sozlanmagan. Adminga xabar berildi.",
                              "❗ Claude API kaliti yo'q yoki noto'g'ri. .env dagi ANTHROPIC_API_KEY ni tekshiring.")
    except anthropic.RateLimitError:
        api_stats.bump("claude", "rate_limited")
        raise GenerationError("AI hozir band. Bir daqiqadan so'ng qayta urinib ko'ring.")
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e.message).lower():
            logging.error("Claude hisobida kredit tugadi")
            api_stats.set_state("claude", error="Hisobda kredit tugadi — balansni to'ldiring", error_at=now_str())
            raise GenerationError(
                "AI xizmati vaqtincha ishlamayapti. Adminga xabar berildi, tez orada tiklanadi.",
                "❗ <b>Claude hisobida kredit tugadi!</b>\nBot taqdimot va referat yarata olmayapti — "
                "console.anthropic.com da balansni to'ldiring.",
            )
        logging.exception("Claude API xatosi: %s", e.status_code)
        raise GenerationError("AI xizmatida vaqtinchalik nosozlik. Birozdan so'ng qayta urinib ko'ring.")
    except anthropic.APITimeoutError:
        logging.warning("Claude API javobi kechikdi (timeout)")
        raise GenerationError("AI javob berishi juda uzoq cho'zildi. Birozdan so'ng qayta urinib ko'ring.")
    except anthropic.APIConnectionError:
        logging.exception("Claude API bilan aloqa yo'q")
        raise GenerationError("AI xizmatiga ulanib bo'lmadi. Birozdan so'ng qayta urinib ko'ring.")


def response_text(response):
    # Agar zaxira model ishga tushgan bo'lsa, faqat oxirgi "fallback" blokdan keyingi matn olinadi
    blocks = list(response.content)
    for i in range(len(blocks) - 1, -1, -1):
        if blocks[i].type == "fallback":
            blocks = blocks[i + 1:]
            break
    return "".join(block.text for block in blocks if block.type == "text")


RATE_LIMIT_WAITS = (5, 10, 20)  # daqiqalik token limitiga urilsa — kutib qayta urinish (soniya)


async def _stream(system, prompt, schema, max_tokens, effort, model, timeout=None, max_retries=None):
    api = client()
    if timeout is not None or max_retries is not None:
        # So'rov uchun alohida chegara (AI yordamchi: 90 s, tarmoq xatosida 1 marta qayta urinish)
        options = {k: v for k, v in (("timeout", timeout), ("max_retries", max_retries)) if v is not None}
        api = api.with_options(**options)
    params = dict(
        model=model,
        max_tokens=max_tokens,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if model.startswith("claude-haiku"):
        # Haiku'da server tomonidagi zaxira model (fallbacks) yo'q — oddiy so'rov
        async with api.messages.stream(**params) as stream:
            return await stream.get_final_message()
    # Rad etilsa (refusal) server o'zi zaxira modelda qayta urinadi
    async with api.beta.messages.stream(
        **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
    ) as stream:
        return await stream.get_final_message()


async def ask_json(system, prompt, schema, max_tokens=4000, effort="low", model=AI_MODEL, timeout=None, max_retries=None):
    """Claude'dan JSON javob oladi. JSON buzilgan bo'lsa None; rad etilsa yoki API xatosi bo'lsa GenerationError.
    effort="low" — model kam «o'ylaydi», javob ancha tez keladi. model — AI_MODEL (reja) yoki AI_MODEL_WRITER (matn).
    timeout / max_retries — shu so'rov uchun (berilmasa — mijozning standart sozlamasi)."""
    options = (timeout, max_retries)
    # Kunlik xarajat chegarasi (ai_usage.py) — yetgan bo'lsa so'rov yuborilmaydi, pul sarflanmaydi
    if ai_usage.over_budget():
        await ai_usage.notify_admin(
            "limit",
            f"⛔️ <b>Claude kunlik chegarasi tugadi</b> (${ai_usage.AI_DAILY_BUDGET_USD:.2f}). Bot bugun AI ishlarini "
            "to'xtatdi.\nKo'paytirish: .env → AI_DAILY_BUDGET_USD, keyin botni qayta ishga tushiring. Sarf: /xarajat",
        )
        raise GenerationError("AI xizmati bugun band. Iltimos, ertaga qayta urinib ko'ring.")
    async with API_SLOTS:
        with api_errors():
            for wait in RATE_LIMIT_WAITS:
                try:
                    response = await _stream(system, prompt, schema, max_tokens, effort, model, *options)
                    break
                except anthropic.RateLimitError as e:
                    # Bir nechta katta buyurtma bir vaqtga to'g'ri kelsa — darhol voz kechmaymiz
                    logging.warning("Claude rate limit, %s s kutamiz: %s", wait, e.message)
                    api_stats.bump("claude", "rate_limited")
                    await asyncio.sleep(wait)
            else:
                response = await _stream(system, prompt, schema, max_tokens, effort, model, *options)
    # Har bir javob narxi yoziladi (rad etilgani ham pulli) — /xarajat
    ai_usage.record(getattr(response, "model", None) or model, getattr(response, "usage", None))
    api_stats.set_state("claude", error=None, error_at=None)  # javob keldi — oldingi xato o'tib ketgan
    await ai_usage.after_request()
    if response.stop_reason == "refusal":
        raise GenerationError("Bu mavzuda ish tayyorlab bo'lmaydi. Boshqa mavzu tanlang.")
    try:
        return json.loads(response_text(response))
    except json.JSONDecodeError:
        logging.warning("AI javobi JSON emas (stop_reason=%s)", response.stop_reason)
        return None


async def run_all(*coroutines):
    """Hammasini parallel bajaradi; bittasi xato bersa qolganlari darhol to'xtatiladi (bekorga token sarflanmasin)."""
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(c) for c in coroutines]
    except ExceptionGroup as errors:
        raise next((e for e in errors.exceptions if isinstance(e, GenerationError)), errors.exceptions[0])
    return [task.result() for task in tasks]


def split_slides(total, plans):
    """Umumiy slaydlar sonidan har bir rejaga nechta kontent slaydi tushishini hisoblaydi.
    4 ta slayd doim bor: muqova, mundarija, reja va xulosa."""
    content = total - FIXED_SLIDES
    base, extra = divmod(content, plans)
    return [base + (1 if i < extra else 0) for i in range(plans)]


def clean(value):
    return " ".join((value or "").split())


def normalize_slide(slide):
    """AI javobidagi kamchiliklarni tuzatadi: maketga elementlar yetmasa — oddiy ro'yxatga o'tkazadi."""
    title, intro = clean(slide.get("title")) or "—", clean(slide.get("text"))
    items = []
    for item in slide.get("items") or []:
        heading, body = clean(item.get("heading")), clean(item.get("text"))
        if body or heading:
            items.append({"heading": heading if body else "", "text": body or heading})
    kind = slide.get("kind") if slide.get("kind") in KINDS else "bullets"
    if kind == "quote" and not intro:
        kind = "bullets"
    if kind not in ("quote", "bullets") and len(items) < ITEM_LIMITS[kind][0]:
        kind = "bullets"
    if kind == "bullets" and not items:
        items, intro = [{"heading": "", "text": intro or title}], ""
    return {
        "title": title, "kind": kind, "text": intro, "items": items[:ITEM_LIMITS[kind][1]],
        "image_query": clean(slide.get("image_query")) or title,
        "image_prompt": clean(slide.get("image_prompt")),
    }


# ===== 1. Reja: avval reja bandlari, keyin har bir bandning slayd sarlavhalari (parallel) =====
async def make_plans(topic, count, lang):
    prompt = (
        f"Topic: {topic}\n"
        f"Language: {LANGUAGE_PROMPT[lang]} (except image_query and image_prompt)\n\n"
        f"Give: `plans` — exactly {count} plan items (the presentation outline, each at most 7 words, "
        "in logical order); `title` — a polished presentation title; `subtitle` — one short line; "
        "`image_query` — 2-4 ENGLISH words for a stock photo for the cover: the first word is the most distinctive "
        "subject, concrete and photographable; real names for famous places or people; for history, culture or a "
        "specific country anchor it to the real region and era (\"Timurid\", \"Samarkand\", \"Uzbekistan\"); "
        "`image_prompt` — ONE English sentence (25-45 words) for an AI image generator: an iconic cover scene for the "
        "topic with faithful historical and cultural details (era, region, people's appearance, clothing, architecture, "
        "landscape); never generic European or fantasy imagery unless the topic is about it; no text or letters."
    )
    for attempt in range(2):
        data = await ask_json(OUTLINE_SYSTEM, prompt, PLANS_SCHEMA, max_tokens=2000)
        plans = [clean(p) for p in (data or {}).get("plans") or [] if clean(p)]
        if len(plans) >= count:
            return {
                "title": clean(data.get("title")) or topic,
                "subtitle": clean(data.get("subtitle")),
                "image_query": clean(data.get("image_query")),
                "image_prompt": clean(data.get("image_prompt")),
                "plans": [{"title": title} for title in plans[:count]],
            }
        logging.warning("AI reja bandlari sonini noto'g'ri qaytardi, urinish %s", attempt + 1)
    raise GenerationError("Taqdimot rejasini tuzib bo'lmadi. Iltimos, qayta urinib ko'ring.")


async def make_slide_titles(topic, lang, outline, number, count):
    plan = outline["plans"][number - 1]
    all_plans = "\n".join(f"{i}. {p['title']}" for i, p in enumerate(outline["plans"], 1))
    quote_rule = "You may use kind \"quote\" at most once." if number == 1 else "Do not use kind \"quote\"."
    prompt = (
        f"Topic: {topic}\nPresentation: {outline['title']}\nLanguage of titles: {LANGUAGE_PROMPT[lang]}\n"
        f"All plan items (others are planned separately):\n{all_plans}\n\n"
        f"Give exactly {count} slides for plan item {number} «{plan['title']}»: a title and a layout kind for each. "
        f"{quote_rule}"
    )
    for _ in range(2):
        slides = (await ask_json(OUTLINE_SYSTEM, prompt, SLIDE_TITLES_SCHEMA, max_tokens=3000) or {}).get("slides") or []
        if len(slides) >= count:
            plan["slides"] = [{"title": clean(s.get("title")) or "—", "kind": s.get("kind")} for s in slides[:count]]
            return
        logging.warning("AI %s-reja slaydlari sonini noto'g'ri qaytardi", number)
    raise GenerationError("Taqdimot rejasini tuzib bo'lmadi. Iltimos, qayta urinib ko'ring.")


async def make_outline(topic, counts, lang):
    outline = await make_plans(topic, len(counts), lang)
    await run_all(*(make_slide_titles(topic, lang, outline, i, n) for i, n in enumerate(counts, 1)))
    return outline


def outline_text(outline):
    return "\n".join(
        f"{i}. {plan['title']}: " + "; ".join(s["title"] for s in plan["slides"])
        for i, plan in enumerate(outline["plans"], 1)
    )


# ===== 2. Slaydlar matni (bo'laklab, parallel) =====
async def write_chunk(topic, lang, outline, chunk):
    """chunk — [(reja_raqami, slayd_dict), ...]; slaydlarni joyida to'ldiradi."""
    wanted = "\n".join(f"{n}. Plan item «{outline['plans'][p]['title']}» → slide «{s['title']}» (kind: {s['kind']})"
                       for n, (p, s) in enumerate(chunk, 1))
    prompt = (
        f"Topic: {topic}\nPresentation: {outline['title']}\n"
        f"Language of all texts (except image_query and image_prompt): {LANGUAGE_PROMPT[lang]}\n\n"
        f"Full outline (for context, other slides are written separately):\n{outline_text(outline)}\n\n"
        f"Write exactly {len(chunk)} slides, in this order:\n{wanted}"
    )
    for _ in range(2):
        data = await ask_json(SLIDES_SYSTEM, prompt, CHUNK_SCHEMA, max_tokens=8000, model=AI_MODEL_WRITER)
        written = (data or {}).get("slides") or []
        if len(written) >= len(chunk):
            for (_, slide), result in zip(chunk, written):
                slide.update(normalize_slide({**result, "title": slide["title"], "kind": slide["kind"]}))
            return
        logging.warning("AI slaydlar bo'lagini to'liq yozmadi")
    raise GenerationError("Kontentni tayyorlab bo'lmadi. Iltimos, qayta urinib ko'ring.")


async def write_conclusion(topic, lang, outline):
    prompt = (
        f"Topic: {topic}\nPresentation: {outline['title']}\nOutline:\n{outline_text(outline)}\n\n"
        f"Write `conclusion` — 3-4 short concluding sentences (at most 18 words each) in {LANGUAGE_PROMPT[lang]}."
    )
    data = await ask_json(SLIDES_SYSTEM, prompt, CONCLUSION_SCHEMA, max_tokens=4000, model=AI_MODEL_WRITER)
    return [clean(c) for c in (data or {}).get("conclusion") or [] if clean(c)] or ["—"]


# Rasm yonida maketi o'zgarmaydigan slaydlar. «cards», «timeline» va katta «stats» rasm bilan oddiy ro'yxatga
# aylanadi (builder.py → content_slide) — shuning uchun rasm avval shu turdagi slaydlarga qo'yiladi
IMAGE_FRIENDLY = ("bullets", "quote")


def image_slots(flat, count, skip=()):
    """Rasm qo'yiladigan slaydlar (indekslar): taqdimot bo'ylab teng taqsimlangan, avval maketi rasm bilan
    buzilmaydiganlar, yetmasa — qolganlari. skip — tanlanmaydiganlar."""
    good = [i for i, (_, s) in enumerate(flat) if s.get("kind") in IMAGE_FRIENDLY and i not in skip]
    rest = [i for i in range(len(flat)) if i not in skip and i not in set(good)]
    picked = [good[j] for j in spread(len(good), count)]
    if len(picked) < count:
        picked += [rest[j] for j in spread(len(rest), count - len(picked))]
    return sorted(picked)


def picture_target(item):
    """Slayd (yoki muqova) → (fotobaza so'rovi, AI uchun sahna tavsifi, sarlavha)."""
    return item["image_query"], item.get("image_prompt") or item["image_query"], item["title"]


# Shablonsiz dizaynlarda fotobazadan mos rasm topilmasa — AI shu uslubda «foto» chizadi (umumiy mavzu rasmi o'rniga)
PHOTO_STYLE = ("photorealistic professional editorial photograph, natural light, sharp focus, rich true-to-life "
               "colors, documentary style, high detail")

VERIFY_SYSTEM = """You are a strict picture editor choosing images for school and university presentations,
reports and theses in Uzbekistan. You see one candidate image and the slide or section it would go on.
First describe in `shows` what the image actually shows (main subject, setting, people, any visible text).
Then decide `fits`.

fits = true if a teacher would accept the image next to this slide/section: it shows the slide's own subject, OR —
when the slide is abstract (theory, strategy, risks, results, conclusions) — the concrete real-world subject of the
whole work (its people, workplaces, objects, places or activities; e.g. a shop owner or a bazaar stall for any section
of a paper about small business). Relevant, decent, natural photos are GOOD — do not reject them for being "stock".

fits = false only if one of these clear failures is true:
- it shows something unrelated to both the slide and the topic, or a symbolic metaphor object instead of the subject
  (chess board for "strategy", hourglass for "risks", light bulb for "ideas", puzzle pieces, arrows, piles of money);
- it shows a person with no visible relation to the topic (someone posing, sitting on a sofa, a portrait);
- it shows a recognizable real person — politician, official, celebrity, public figure — unless the slide is
  explicitly about that person;
- the topic is about a specific country, culture or era and the image clearly shows another one (e.g. an Indian
  street, Western knights for Central Asian history, a different famous city);
- prominent readable text, slogans, captions, watermarks, logos or brand names, charts, maps with labels,
  screenshots, collages, clipart or cartoons;
- inappropriate, violent, disturbing or unsuitable for students; very low quality, blurry or distorted."""

VERIFY_DRAWN = (
    "This image was generated by AI from this slide's own description, so its subject is intended. Accept it "
    "(fits = true) unless it has a defect: readable or gibberish text/letters/logos, malformed faces, hands, bodies "
    "or objects, a clearly wrong country/culture/era for the topic, something clearly unrelated, or content "
    "unsuitable for students."
)

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"shows": {"type": "string"}, "fits": {"type": "boolean"}},
    "required": ["shows", "fits"],
    "additionalProperties": False,
}
VERIFY_SIDE = 448  # tekshirish uchun kichik nusxa — tez va arzon (~250 token)


def thumbnail_b64(image):
    with Image.open(io.BytesIO(image)) as picture:
        picture = picture.convert("RGB")
        picture.thumbnail((VERIFY_SIDE, VERIFY_SIDE))
        buffer = io.BytesIO()
        picture.save(buffer, "JPEG", quality=70)
    return base64.b64encode(buffer.getvalue()).decode()


def slide_brief(slide):
    """Tekshiruvchi uchun slaydning qisqa mazmuni."""
    points = "; ".join(" ".join(filter(None, (i.get("heading"), i.get("text")))) for i in slide.get("items", [])[:3])
    return " ".join(filter(None, (slide.get("text"), points)))[:500]


def photo_checker(topic, outline, slide, extra=""):
    """Slayd uchun AI tekshiruv funksiyasi: rasmni Claude (Haiku, arzon) ko'rib, mos/mos emas deydi.
    Xato bo'lsa None qaytadi — shunda faqat teglari aniq mos rasm olinadi. extra — qo'shimcha qoida (maqola)."""
    async def check(image, drawn=False):
        """drawn=True — AI chizgan rasm: faqat nuqsonlar tekshiriladi (mavzusi tavsifdan chizilgan)."""
        data = await asyncio.to_thread(thumbnail_b64, image)
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
            {"type": "text", "text": (
                f"Presentation topic: {topic}\nPresentation title: {outline.get('title', topic)}\n"
                f"Slide title: {slide.get('title', '')}\nSlide content: {slide_brief(slide)}\n"
                f"Wanted picture: {slide.get('image_query', '')}. {slide.get('image_prompt', '')}\n\n"
                + (f"{extra}\n" if extra else "")
                + (f"{VERIFY_DRAWN}\n" if drawn else "")
                + ("Does this image fit this slide?" if drawn else "Does this photo fit this slide?")
            )},
        ]
        try:
            result = await ask_json(VERIFY_SYSTEM, content, VERIFY_SCHEMA, max_tokens=1500,
                                    model=AI_MODEL_WRITER, timeout=25, max_retries=1)
        except GenerationError:
            return None
        if not isinstance(result, dict) or "fits" not in result:
            return None
        if not result["fits"]:
            logging.info("Rasm rad etildi: «%s» — %s", slide.get("title"), str(result.get("shows", ""))[:160])
        return bool(result["fits"])
    return check


REDRAW_HINT = (" Show the subject literally and realistically, exactly as described; no symbolic or metaphorical "
               "objects, no text of any kind.")


async def draw_verified(prompts, checks):
    """AI rasm chizadi va har birini tekshiradi (check). Mos kelmaganini bir marta aniqroq tavsif bilan qayta chizadi;
    yana mos kelmasa — None. Tekshirib bo'lmasa (AI javob bermadi) — chizilgan rasm qoldiriladi: u aynan shu
    slayd/bo'lim tavsifi bo'yicha chizilgan. Hech qachon xato tashlamaydi."""
    if not prompts or not genimage.enabled():
        return [None] * len(prompts)

    async def verdicts(images, indices):
        async def one(i):
            if not images[i] or checks[i] is None:
                return images[i] is not None
            try:
                verdict = await checks[i](images[i], drawn=True)
            except Exception:  # noqa: BLE001
                verdict = None
            return True if verdict is None else verdict
        return await asyncio.gather(*(one(i) for i in indices))

    made = await genimage.generate_images(prompts)
    rejected = [i for i, ok in zip(range(len(made)), await verdicts(made, range(len(made)))) if made[i] and not ok]
    if rejected:
        logging.info("AI rasmi tekshiruvdan o'tmadi, qayta chiziladi: %s ta", len(rejected))
        again = await genimage.generate_images([prompts[i] + REDRAW_HINT for i in rejected])
        retry = list(made)
        for i, image in zip(rejected, again):
            retry[i] = image
        for i, ok in zip(rejected, await verdicts(retry, rejected)):
            made[i] = retry[i] if ok else None
    return made


async def pictures(slides, used, topic, outline, style=None, fallback=None):
    """slides — rasm kerak bo'lgan slaydlar → rasmlar (yoki None), har biri AI tekshiruvidan o'tgan.
    Shablon (style) bo'lsa — rasmlar shu uslubda AI bilan chiziladi, chizilmaganlari foto qidiruvi bilan to'ldiriladi;
    aks holda — foto qidiruvi. fallback — mavzu bo'yicha so'rov (oxirgi chora). Hech qachon xato tashlamaydi."""
    if not slides:
        return []
    targets = [picture_target(s) for s in slides]
    checks = [photo_checker(topic, outline, s) for s in slides]
    if style and genimage.enabled():
        made = await draw_verified([genimage.prompt_for(p, c, topic, style) for _, p, c in targets], checks)
        missing = [i for i, image in enumerate(made) if not image]
        if missing:
            found = await find_images([targets[i][0] for i in missing], used, fallback, [checks[i] for i in missing])
            for i, image in zip(missing, found):
                made[i] = image
        return made
    return await find_images([q for q, _, _ in targets], used, fallback, checks)


async def draw_missing(slides, topic, style=None, outline=None):
    """Fotobazadan mos rasm topilmagan slaydlarga AI aynan slayd mazmuni bo'yicha rasm chizadi (tekshiruv bilan)."""
    if not slides or not genimage.enabled():
        return [None] * len(slides)
    prompts = [genimage.prompt_for(p, c, topic, style or PHOTO_STYLE) for _, p, c in map(picture_target, slides)]
    checks = [photo_checker(topic, outline or {"title": topic}, s) for s in slides]
    return await draw_verified(prompts, checks)


async def best_pictures(targets, topic, title=None, draw_prompt=None, prefer_ai=False, fallback=None):
    """Referat, kurs ishi, diplom va dissertatsiya uchun: har bir target (dict: title, text, image_query,
    image_prompt) ga mavzuga mos rasm. Har bir rasm — foto ham, AI chizgani ham — AI tekshiruvidan o'tadi.
    Tartib: fotobaza (Pexels → Pixabay → Wikimedia), mos foto bo'lmasa — AI aynan shu bo'lim mazmuni bo'yicha chizadi.
    prefer_ai=True — avval AI chizadi, chiza olmasa foto (ilmiy ish illyustratsiyalari uchun).
    draw_prompt(target) — AI uchun so'rov (berilmasa — fotorealistik, prompt_for bilan).
    Qaytaradi: [(rasm yoki None, "photo" | "ai" | None), ...]. Hech qachon xato tashlamaydi."""
    if not targets:
        return []
    outline = {"title": title or topic}
    checks = [photo_checker(topic, outline, t) for t in targets]
    prompt = draw_prompt or (lambda t: genimage.prompt_for(t.get("image_prompt") or t["image_query"], t["title"],
                                                           topic, PHOTO_STYLE))
    result = [(None, None)] * len(targets)
    used = set()

    async def photos(indices, query=None):
        found = await find_images([query or targets[i]["image_query"] for i in indices], used,
                                  None if query else fallback, [checks[i] for i in indices])
        for i, image in zip(indices, found):
            if image:
                result[i] = (image, "photo")

    async def drawings(indices):
        drawn = await draw_verified([prompt(targets[i]) for i in indices], [checks[i] for i in indices])
        for i, image in zip(indices, drawn):
            if image:
                result[i] = (image, "ai")

    def missing():
        return [i for i, (image, _) in enumerate(result) if not image]

    try:
        first, second = (drawings, photos) if prefer_ai else (photos, drawings)
        await first(list(range(len(targets))))
        if missing():
            await second(missing())
        # Oxirgi chora — butun ish mavzusi bo'yicha foto (baribir AI tekshiruvi bilan): rasmlar kamayib ketmasin
        if missing() and fallback:
            await photos(missing(), fallback)
    except Exception:  # noqa: BLE001 — rasm sababli hujjat to'xtamasin
        logging.exception("Rasmlarni tanlashda xato")
    return result


async def generate_content(topic, plans, slides, lang, images=0, theme=None):
    """Taqdimot matni va rasmlari. (content, qo'yilgan_rasmlar_soni) qaytaradi.
    images — jami rasmlar soni: hammasi ichki mavzu slaydlariga teng taqsimlanadi. Muqova, mundarija, reja va
    xulosa slaydlariga rasm qo'yilmaydi (muqovada o'rniga bezak kompozitsiya chiziladi).
    theme — dizayn: shablon bo'lsa, rasmlar uning uslubida generatsiya qilinadi (themes.py → image_style).
    Rasmlar hech qachon xato tashlamaydi va buyurtmani kechiktirmaydi (ichida vaqt chegarasi bor)."""
    outline = await make_outline(topic, split_slides(slides, plans), lang)
    flat = [(p, slide) for p, plan in enumerate(outline["plans"]) for slide in plan["slides"]]
    images = max(0, min(images, len(flat)))
    with_image = set(image_slots(flat, images))
    used = set()
    topic_query = outline["image_query"]  # umumiy mavzu rasmi — faqat oxirgi chora
    style = THEMES.get(theme, {}).get("image_style")

    async def chunk_job(start):
        chunk = flat[start:start + CHUNK]
        await write_chunk(topic, lang, outline, chunk)
        # Bo'lak tayyor bo'lishi bilan uning rasmlarini olamiz — matn yozilayotgan paytda.
        # Faqat slaydning O'Z mavzusi bo'yicha va har bir rasm AI tekshiruvidan o'tadi (mavzuga mos bo'lmasa — olinmaydi)
        targets = [slide for i, (_, slide) in enumerate(chunk, start) if i in with_image]
        for slide, image in zip(targets, await pictures(targets, used, topic, outline, style)):
            slide["image"] = image

    async def cover_job():
        """Tabiat shablonlarida muqova — butun slaydli foto (themes.py → cover_photo). Qolganlarida muqova rasmsiz."""
        if not THEMES.get(theme, {}).get("cover_photo") or not outline.get("image_query"):
            return None
        cover = {"title": outline["title"], "text": outline.get("subtitle", ""), "items": [],
                 "image_query": outline["image_query"], "image_prompt": outline.get("image_prompt", "")}
        image = (await pictures([cover], used, topic, outline, style))[0]
        if not image:
            image = (await draw_missing([cover], topic, style, outline))[0]
        return image

    *_, conclusion, cover_image = await run_all(
        *(chunk_job(i) for i in range(0, len(flat), CHUNK)), write_conclusion(topic, lang, outline), cover_job()
    )
    outline["conclusion"] = conclusion
    outline["cover_image"] = cover_image  # klassik dizaynlarda None — bezak kompozitsiya bilan

    def empty_selected():
        return [flat[i][1] for i in sorted(with_image) if not flat[i][1].get("image")]

    def put(slides, found_images):
        for slide, image in zip(slides, found_images):
            if image:
                slide["image"] = image

    # 1) Mos foto topilmagan slaydlarga AI aynan shu slayd mazmuni bo'yicha rasm chizadi (umumiy rasm o'rniga)
    put(empty_selected(), await draw_missing(empty_selected(), topic, style, outline))
    # 2) Shunda ham kam bo'lsa — boshqa slaydlarning o'z mavzusi bo'yicha (tekshirilgan) foto qidiramiz
    missing = images - sum(1 for _, s in flat if s.get("image"))
    if missing > 0:
        extra = [flat[i][1] for i in image_slots(flat, missing, skip=with_image)]
        put(extra, await pictures(extra, used, topic, outline, style))
    # 3) Oxirgi chora — rasmsiz qolgan tanlangan slaydlarga mavzu bo'yicha foto, lekin baribir AI tekshiruvi bilan
    missing = images - sum(1 for _, s in flat if s.get("image"))
    if missing > 0 and topic_query:
        empty = empty_selected()[:missing]
        put(empty, await pictures(empty, used, topic, outline, None, topic_query))
    return outline, sum(1 for _, s in flat if s.get("image"))
