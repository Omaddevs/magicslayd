"""AI yordamchining umumiy servisi — sayt va bot shu funksiyalardan foydalanadi:
validate() → check_limits() → run() (AI + fayllar + log). Promptlar: assistant/prompts.py, fayllar: assistant/files.py."""
import hashlib
import html
import logging
import re
import time
import unicodedata

from assistant import prompts
from config import AI_ASSISTANT_DAILY_LIMIT, AI_ASSISTANT_MODEL, AI_ASSISTANT_PER_MINUTE, AI_ASSISTANT_TIMEOUT
from database import ai_request_finish, ai_request_start, ai_usage
from presentation.ai import GenerationError, ask_json, run_all

log = logging.getLogger("assistant")

# Ish turlari va hajm chegaralari (sayt formasi ham shundan quriladi — web_config orqali)
TYPES = {
    "pres": {"label": "Taqdimot", "unit": "slayd", "min": 5, "max": 20, "default": 10},
    "referat": {"label": "Referat", "unit": "bet", "min": 5, "max": 20, "default": 10},
    "mustaqil": {"label": "Mustaqil ish", "unit": "bet", "min": 5, "max": 15, "default": 8},
    "kurs": {"label": "Kurs ishi", "unit": "bet", "min": 15, "max": 40, "default": 25},
}
LANGUAGES = {"uz": "O'zbek (lotin)", "uz_cyrl": "Ўзбек (кирилл)", "ru": "Русский"}
TOPIC_MIN, TOPIC_MAX, SUBJECT_MAX = 5, 200, 100
WORDS_PER_PAGE = 250
LIMIT_TEXT = "Bugungi bepul limitingiz tugadi. Ertaga qayta urinib ko'ring."
RATE_TEXT = "Juda tez so'rov yuboryapsiz. Bir daqiqadan so'ng qayta urinib ko'ring."


class AssistantError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato (o'zbekcha). code — log va API uchun qisqa tur, field — forma maydoni."""

    def __init__(self, message, code="error", field=None):
        super().__init__(message)
        self.code = code
        self.field = field


def public_settings():
    """Sayt formasi va server validatsiyasi uchun (bot ishga tushganda web_config ga yoziladi)."""
    return {
        "types": TYPES, "languages": LANGUAGES, "topic_min": TOPIC_MIN, "topic_max": TOPIC_MAX,
        "subject_max": SUBJECT_MAX, "daily_limit": AI_ASSISTANT_DAILY_LIMIT, "per_minute": AI_ASSISTANT_PER_MINUTE,
    }


# ===== Kiruvchi ma'lumotni tozalash va tekshirish =====
def clean_text(value):
    """HTML teglari, boshqaruv belgilari va <> olib tashlanadi; bo'shliqlar bittaga. Prompt va sahifa uchun xavfsiz."""
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]*>", " ", text)
    text = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in text)
    text = text.replace("<", " ").replace(">", " ")
    return re.sub(r"\s+", " ", text).strip()


def validate(data):
    """{type, topic, subject, size, language} → tozalangan parametrlar. Xato bo'lsa AssistantError(field=...)."""
    kind = data.get("type")
    if kind not in TYPES:
        raise AssistantError("Ish turini tanlang.", "validation", "type")
    topic = clean_text(data.get("topic"))
    if len(topic) < TOPIC_MIN:
        raise AssistantError(f"Mavzu kamida {TOPIC_MIN} ta belgidan iborat bo'lsin.", "validation", "topic")
    if len(topic) > TOPIC_MAX:
        raise AssistantError(f"Mavzu {TOPIC_MAX} belgidan oshmasin.", "validation", "topic")
    subject = clean_text(data.get("subject"))
    if len(subject) > SUBJECT_MAX:
        raise AssistantError(f"Fan nomi {SUBJECT_MAX} belgidan oshmasin.", "validation", "subject")
    rules = TYPES[kind]
    size = data.get("size", rules["default"])
    if isinstance(size, str) and size.strip().isdecimal():
        size = int(size)
    if not isinstance(size, int) or isinstance(size, bool) or not rules["min"] <= size <= rules["max"]:
        raise AssistantError(
            f"{rules['label']} hajmi {rules['min']}–{rules['max']} {rules['unit']} oralig'ida bo'lsin.", "validation", "size"
        )
    language = data.get("language", "uz")
    if language not in LANGUAGES:
        raise AssistantError("Tilni tanlang.", "validation", "language")
    return {"type": kind, "topic": topic, "subject": subject, "size": size, "language": language}


# ===== Limitlar =====
def daily_limit(user_key):
    """Kunlik bepul limit. Pullik tarif qo'shilganda shu yerda userning tarifi tekshiriladi."""
    return AI_ASSISTANT_DAILY_LIMIT


def check_limits(user_key):
    """Limit tugagan yoki juda tez so'ralgan bo'lsa AssistantError. Aks holda bugun qolgan bepul so'rovlar soni."""
    today, recent = ai_usage(user_key)
    if recent >= AI_ASSISTANT_PER_MINUTE:
        raise AssistantError(RATE_TEXT, "rate_limit")
    limit = daily_limit(user_key)
    if today >= limit:
        raise AssistantError(LIMIT_TEXT, "daily_limit")
    return limit - today


def remaining(user_key):
    return max(0, daily_limit(user_key) - ai_usage(user_key)[0])


# ===== AI javobini tekshirish =====
def _text(value, limit):
    text = clean_text(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _strings(values, limit):
    return [s for s in (_text(v, limit) for v in (values if isinstance(values, list) else [])) if s]


def check_presentation(data, count):
    """{"title", "slides": [{"title", "bullets"}]} — slaydlar soni kamida count-1 bo'lsa qabul, ortig'i kesiladi."""
    title = _text(data.get("title"), 200)
    slides = []
    for slide in data.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        heading, bullets = _text(slide.get("title"), 150), _strings(slide.get("bullets"), 300)[:6]
        if heading and len(bullets) >= 2:
            slides.append({"title": heading, "bullets": bullets})
    if not title or len(slides) < max(1, count - 1):
        return None
    return {"title": title, "slides": slides[:count]}


def check_outline(data, chapters, nested):
    title = _text(data.get("title"), 250)
    parts = []
    for chapter in data.get("chapters") or []:
        if not isinstance(chapter, dict) or not _text(chapter.get("title"), 200):
            continue
        sections = _strings(chapter.get("sections"), 200)[:2] if nested else []
        if nested and len(sections) < 2:
            return None
        parts.append({"title": _text(chapter.get("title"), 200), "sections": sections})
    references = _strings(data.get("references"), 400)[:10]
    if not title or len(parts) < chapters or len(references) < 3:
        return None
    return {"title": title, "chapters": parts[:chapters], "references": references}


def check_section(data):
    paragraphs = [p for p in (clean_text(p) for p in (data.get("paragraphs") or [])) if p]
    return "\n\n".join(paragraphs) if paragraphs else None


# ===== JSON sxemalar (structured outputs) =====
_STRINGS = {"type": "array", "items": {"type": "string"}}


def _object(**properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


PRESENTATION_SCHEMA = _object(title={"type": "string"}, slides={"type": "array", "items": _object(
    title={"type": "string"}, bullets=_STRINGS)})
OUTLINE_SCHEMA = _object(title={"type": "string"}, chapters={"type": "array", "items": _object(
    title={"type": "string"}, sections=_STRINGS)}, references=_STRINGS)
SECTION_SCHEMA = _object(paragraphs=_STRINGS)


async def ask(prompt, schema, check, max_tokens):
    """AI'dan JSON so'raydi va tekshiradi. Buzilgan bo'lsa 1 marta qayta so'raydi, bo'lmasa AssistantError."""
    for attempt in (1, 2):
        data = await ask_json(
            prompts.SYSTEM, prompt, schema, max_tokens=max_tokens, effort="low", model=AI_ASSISTANT_MODEL,
            timeout=AI_ASSISTANT_TIMEOUT, max_retries=1,
        )
        result = check(data) if isinstance(data, dict) else None
        if result is not None:
            return result
        log.warning("AI javobi talabga mos emas (urinish %s)", attempt)
    raise AssistantError("AI javobini o'qib bo'lmadi. Iltimos, qayta urinib ko'ring.", "bad_json")


# ===== Yaratish =====
def _base(params):
    return {
        "topic": params["topic"], "subject": params["subject"] or "—",
        "language": prompts.LANGUAGE_RULES[params["language"]],
    }


async def make_presentation(params):
    count = params["size"] - 1  # muqova alohida qo'shiladi: jami slaydlar = size
    prompt = prompts.PRESENTATION.format(**_base(params), count=count)
    return await ask(prompt, PRESENTATION_SCHEMA, lambda d: check_presentation(d, count), max_tokens=8000)


def document_shape(kind, pages):
    """(asosiy qismlar soni, kurs ishidagi kabi ichki bo'limlar bormi)."""
    if kind == "kurs":
        return (3 if pages >= 30 else 2), True
    return (3 if pages > 8 else 2), False


async def make_document(params):
    kind, lang, pages = params["type"], params["language"], params["size"]
    labels = prompts.LABELS[lang]
    chapters, nested = document_shape(kind, pages)
    base = {**_base(params), "kind": prompts.DOCUMENT_KINDS[kind]}

    outline = await ask(
        prompts.OUTLINE.format(**base, chapters=chapters, sections_rule=prompts.SECTIONS_RULE["nested" if nested else "flat"]),
        OUTLINE_SCHEMA, lambda d: check_outline(d, chapters, nested), max_tokens=4000,
    )

    # Reja: Kirish → boblar (→ bo'limlar) → Xulosa → Adabiyotlar. Matni yoziladiganlari — written
    plan, sections, written = [labels["intro"]], [{"heading": labels["intro"], "content": ""}], []
    written.append((0, prompts.ROLE_INTRO[kind]))
    for i, chapter in enumerate(outline["chapters"], 1):
        if nested:
            heading = f"{labels['chapter'].format(n=i)} {chapter['title']}"
            plan.append(heading)
            sections.append({"heading": heading, "content": ""})  # bob sarlavhasi — matni bo'limlarda
            for j, sub in enumerate(chapter["sections"], 1):
                plan.append(f"{i}.{j}. {sub}")
                sections.append({"heading": f"{i}.{j}. {sub}", "content": ""})
                written.append((len(sections) - 1, prompts.ROLE_BODY))
        else:
            plan.append(f"{i}. {chapter['title']}")
            sections.append({"heading": f"{i}. {chapter['title']}", "content": ""})
            written.append((len(sections) - 1, prompts.ROLE_BODY))
    plan.append(labels["conclusion"])
    sections.append({"heading": labels["conclusion"], "content": ""})
    written.append((len(sections) - 1, prompts.ROLE_CONCLUSION))
    plan.append(labels["references"])

    # So'zlar: titul, reja va adabiyotlar ~2 bet; kirish ~12%, xulosa ~8%, qolgani asosiy bo'limlarga teng
    total = max(pages - 2, 2) * WORDS_PER_PAGE
    body_count = len(written) - 2
    body_words = total * 0.8 / max(body_count, 1)
    plan_text = "\n".join(plan)

    async def write(index, role):
        words = int(total * 0.12) if index == 0 else int(total * 0.08) if role == prompts.ROLE_CONCLUSION else int(body_words)
        words = max(words, 120)
        prompt = prompts.SECTION.format(
            **base, title=outline["title"], plan=plan_text, heading=sections[index]["heading"], role=role, words=words,
        )
        sections[index]["content"] = await ask(prompt, SECTION_SCHEMA, check_section, max_tokens=min(16000, words * 4 + 800))

    await run_all(*(write(index, role) for index, role in written))
    return {"title": outline["title"], "plan": plan, "sections": sections, "references": outline["references"]}


async def generate(params):
    return await (make_presentation(params) if params["type"] == "pres" else make_document(params))


def _user_tag(user_key):
    """Logga user ID o'rniga qisqa xesh — shaxsiy ma'lumot yozilmaydi."""
    return hashlib.sha256(str(user_key).encode()).hexdigest()[:10]


async def run(user_key, source, params, request_id=None):
    """To'liq jarayon: (limit) → AI → fayllar. (natija, fayllar) qaytaradi, xatoda AssistantError.
    request_id — sayt allaqachon limitni tekshirib, so'rovni yozib qo'ygan bo'lsa (handlers/web.py)."""
    from assistant.files import build_files  # python-docx/pptx/pymupdf — faqat kerak bo'lganda yuklanadi

    if request_id is None:
        check_limits(user_key)
        request_id = ai_request_start(user_key, source, params["type"])
    started = time.monotonic()
    status, code = "error", "internal"
    try:
        result = await generate(params)
        files = await build_files(result, params)
        status, code = "ok", None
        return result, files
    except AssistantError as e:
        code = e.code
        raise
    except GenerationError as e:
        code = "ai"
        raise AssistantError(str(e), "ai") from e
    except Exception as e:
        log.exception("AI yordamchida kutilmagan xato")
        raise AssistantError("Kutilmagan xato yuz berdi. Iltimos, qayta urinib ko'ring.", "internal") from e
    finally:
        ai_request_finish(request_id, status, code)
        log.info(
            "AI yordamchi: user=%s source=%s type=%s size=%s lang=%s status=%s%s time=%.1fs",
            _user_tag(user_key), source, params["type"], params["size"], params["language"], status,
            f" error={code}" if code else "", time.monotonic() - started,
        )


def count_words(result):
    if "slides" in result:
        return sum(len(" ".join(s["bullets"]).split()) for s in result["slides"])
    return sum(len(s["content"].split()) for s in result["sections"])
