"""Referat, mustaqil ish va kurs ishi matnini Claude AI orqali yozdiradi.
Tezlik uchun: avval qisqa reja (sarlavhalar) tuziladi, keyin har bir bo'lim, kirish va xulosa 2 xatboshilik
bo'laklarga bo'linib bir vaqtda yoziladi; adabiyotlar va rasmlar ham parallel tayyorlanadi.
O'zbek tilida 1 so'z ~4 token, Claude ~65 token/s yozadi — kichik bo'laklar 50 betni ham ~30 s da tugatadi."""
import logging

from config import AI_MODEL_WRITER
from diploma.figures import figure_prompt
from presentation.ai import LANGUAGE_PROMPT, GenerationError, ask_json, best_pictures, clean, run_all

WORDS_PER_PAGE = 280  # Times New Roman 14, 1.5 interval
PARAGRAPH_WORDS = 100  # Claude «100-150 so'z» deb so'ralganda amalda ~100 so'z yozadi (o'lchangan)
SERVICE_PAGES = 3  # muqova, mundarija, adabiyotlar
PART = 2  # bitta so'rovda nechta xatboshi yoziladi

KIND_PROMPT = {
    "referat": "a referat (an academic report on the topic)",
    "mustaqil": "an independent work (mustaqil ish) — a student's self-study written assignment",
    "kurs": "a course paper (kurs ishi): the first chapter is theoretical, the following chapters are analytical and practical",
}

SYSTEM = """You write academic papers for students of universities, colleges and schools in Uzbekistan.
Write in a formal academic style: coherent, factually accurate, with real substance. No filler and no repetition.
No markdown, no emoji, no bullet characters, and no numbering inside titles — numbering is added automatically.
Follow the exact numbers of chapters, sections and paragraphs that the user asks for."""

_TEXTS = {"type": "array", "items": {"type": "string"}}
OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "image_query": {"type": "string"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "sections": _TEXTS, "image_query": {"type": "string"},
                               "section_queries": _TEXTS},
                "required": ["title", "sections", "image_query", "section_queries"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "image_query", "chapters"],
    "additionalProperties": False,
}
PARAGRAPHS_SCHEMA = {
    "type": "object",
    "properties": {"paragraphs": _TEXTS},
    "required": ["paragraphs"],
    "additionalProperties": False,
}
REFERENCES_SCHEMA = {
    "type": "object",
    "properties": {"references": _TEXTS},
    "required": ["references"],
    "additionalProperties": False,
}


def structure(pages):
    """Betlar sonidan tuzilmani hisoblaydi: boblar, bo'limlar, xatboshilar va adabiyotlar soni."""
    paragraphs = max(6, round(max(2, pages - SERVICE_PAGES) * WORDS_PER_PAGE / PARAGRAPH_WORDS))
    intro = max(1, round(paragraphs * 0.08))
    chapters = 2 if pages <= 7 else 3 if pages <= 35 else 4
    sections = 1 if pages <= 8 else 2 if pages <= 20 else 3 if pages <= 40 else 4
    return {
        "chapters": chapters,
        "sections": sections,
        "paragraphs": max(2, round((paragraphs - 2 * intro) / (chapters * sections))),
        "intro": intro,
        "references": "5-7" if pages <= 10 else "8-12" if pages <= 25 else "12-18",
    }


def head(kind, topic, lang):
    return (
        f"Topic: {topic}\n"
        f"Language of all texts: {LANGUAGE_PROMPT[lang]}\n"
        f"The paper is {KIND_PROMPT[kind]}.\n\n"
    )


def texts(values):
    return [clean(v) for v in values or [] if clean(v)]


# ===== 1. Reja: faqat sarlavhalar =====
async def make_outline(kind, topic, lang, s):
    prompt = head(kind, topic, lang) + (
        "Create the outline of the paper:\n"
        "- `title`: a polished title of the work based on the topic\n"
        "- `image_query`: 2-4 ENGLISH words for searching a stock photo that illustrates the whole topic\n"
        f"- `chapters`: exactly {s['chapters']} chapters, each with exactly {s['sections']} section titles, "
        "`image_query` — 2-4 ENGLISH words for searching a real stock photo that illustrates the chapter, and "
        f"`section_queries` — exactly {s['sections']} such ENGLISH queries, one per section in the same order, each "
        "showing what THAT section is about (all different from each other and from the chapter query)\n"
        "Every image_query starts with the main subject, then details "
        '(e.g. "solar panels on roof", "teacher in classroom", "bakery owner serving customer"); concrete and '
        "photographable — the real people, objects, places or activities the section talks about. Never abstract "
        "ideas or symbolic objects (no chess, hourglass, light bulb, handshake, puzzle, arrows, charts, money piles). "
        'Real names for famous places or people ("Registan Samarkand"). If the topic concerns Uzbekistan, prefer '
        'scenes that also exist there (bazaar, small shop, farm, classroom) and add "Uzbekistan" where it helps.\n'
        "Section titles must not overlap — each covers a different aspect."
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, OUTLINE_SCHEMA, max_tokens=8000)
        chapters = [
            {"title": clean(ch.get("title")) or "—", "sections": texts(ch.get("sections"))[:s["sections"]],
             "image_query": clean(ch.get("image_query")) or clean(ch.get("title")),
             "section_queries": texts(ch.get("section_queries"))[:s["sections"]]}
            for ch in (data or {}).get("chapters") or []
        ][:s["chapters"]]
        if len(chapters) == s["chapters"] and all(len(ch["sections"]) == s["sections"] for ch in chapters):
            return {"title": clean(data.get("title")) or topic, "image_query": clean(data.get("image_query")),
                    "chapters": chapters}
        logging.warning("AI reja (bob/bo'lim) sonini noto'g'ri qaytardi")
    raise GenerationError("Ish rejasini tuzib bo'lmadi. Iltimos, qayta urinib ko'ring.")


def outline_text(outline):
    return "\n".join(
        f"{i}. {ch['title']}: " + "; ".join(f"{i}.{j}. {sec}" for j, sec in enumerate(ch["sections"], 1))
        for i, ch in enumerate(outline["chapters"], 1)
    )


# ===== 2. Matn: 2 xatboshilik bo'laklar, parallel =====
async def write_part(kind, topic, lang, outline, where, task, first, count, total):
    """Bitta bo'lim (yoki kirish/xulosa) ning first..first+count-1 xatboshilarini yozadi."""
    position = (
        "the whole text" if count == total else
        f"paragraphs {first}-{first + count - 1} of {total} (the other paragraphs are written separately: "
        "beginning paragraphs introduce, middle ones develop, final ones conclude — write the ones for your position)"
    )
    prompt = head(kind, topic, lang) + (
        f"Paper title: {outline['title']}\nFull outline:\n{outline_text(outline)}\n\n"
        f"Write {where}: {task}\n"
        f"Write {position}. `paragraphs`: exactly {count} paragraphs of 100-150 words."
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, PARAGRAPHS_SCHEMA, max_tokens=6000, model=AI_MODEL_WRITER)
        written = texts((data or {}).get("paragraphs"))
        if written:
            return written[:count]
        logging.warning("AI matn bo'lagini yozmadi: %s", where)
    raise GenerationError("Matnni tayyorlab bo'lmadi. Iltimos, qayta urinib ko'ring.")


async def write_block(kind, topic, lang, outline, where, task, total):
    """total ta xatboshini PART tadan bo'lib parallel yozadi va tartib bilan birlashtiradi."""
    parts = await run_all(*(
        write_part(kind, topic, lang, outline, where, task, first + 1, min(PART, total - first), total)
        for first in range(0, total, PART)
    ))
    return [paragraph for part in parts for paragraph in part]


async def write_references(kind, topic, lang, outline, count):
    prompt = head(kind, topic, lang) + (
        f"Paper title: {outline['title']}\nOutline:\n{outline_text(outline)}\n\n"
        f"Write `references`: {count} items — only real, well-known textbooks, monographs, laws and official "
        'websites relevant to the topic, formatted as "Author. Title. — City: Publisher, Year." '
        "Never invent sources you are not sure exist."
    )
    data = await ask_json(SYSTEM, prompt, REFERENCES_SCHEMA, max_tokens=4000, model=AI_MODEL_WRITER)
    return texts((data or {}).get("references"))


async def chapter_images(outline, topic):
    """Mavzuga mos rasmlar (takrorlanmaydi): har bir bobga bitta (birinchi bo'limda) va qolgan har bir bo'limga
    bittadan — har biri o'sha bo'lim mavzusi bo'yicha. Har bir rasm AI tekshiruvidan o'tadi (presentation/ai.py →
    best_pictures): mos foto bo'lmasa, AI aynan shu bo'lim mazmuni bo'yicha chizadi — rasmlar kamaymaydi.
    Xato tashlamaydi va vaqt chegarasi bor — hujjat rasm sababli kechikmaydi."""
    places, targets = [], []  # (bob, bo'lim indeksi yoki None), rasm talablari
    for ch in outline["chapters"]:
        queries = ch.get("section_queries") or []
        for si in range(len(ch["sections"])):
            query = ch["image_query"] if si == 0 else (
                queries[si] if si < len(queries) else f"{ch['image_query']} {ch['sections'][si]}")
            section = ch["sections"][si]
            places.append((ch, None if si == 0 else si))
            targets.append({"title": section, "text": f"Chapter: {ch['title']}", "items": [],
                            "image_query": query, "image_prompt": f"{query} — illustrating «{section}»"})
    found = await best_pictures(
        targets, topic, outline["title"], fallback=outline["image_query"] or None,
        draw_prompt=lambda t: figure_prompt(t["image_prompt"], t["title"], topic),
    )
    for (chapter, si), (image, _) in zip(places, found):
        if si is None:
            chapter["image"] = image
        else:
            chapter.setdefault("section_images", {})[si] = image


def word_count(content):
    paragraphs = content["intro"] + content["conclusion"] + [
        p for chapter in content["chapters"] for sec in chapter["sections"] for p in sec["paragraphs"]
    ]
    return sum(len(p.split()) for p in paragraphs)


async def generate_document(kind, topic, lang, pages):
    s = structure(pages)
    outline = await make_outline(kind, topic, lang, s)
    sections = [(i, j, ch, title) for i, ch in enumerate(outline["chapters"], 1) for j, title in enumerate(ch["sections"], 1)]
    intro_task = "the INTRODUCTION — relevance of the topic, goal, tasks, object and subject of the work"
    conclusion_task = "the CONCLUSION — summarize the results of every chapter"
    intro, conclusion, references, *rest = await run_all(
        write_block(kind, topic, lang, outline, "the introduction", intro_task, s["intro"]),
        write_block(kind, topic, lang, outline, "the conclusion", conclusion_task, s["intro"]),
        write_references(kind, topic, lang, outline, s["references"]),
        *(write_block(kind, topic, lang, outline, f"section {i}.{j} «{title}» of chapter {i} «{ch['title']}»",
                      "stay within this section's scope — other sections are written separately", s["paragraphs"])
          for i, j, ch, title in sections),
        chapter_images(outline, topic),
    )
    written = iter(rest[:len(sections)])
    return {
        "title": outline["title"],
        "intro": intro,
        "chapters": [
            {"title": ch["title"], "image": ch.get("image"),
             "sections": [{"title": title, "paragraphs": next(written),
                           "image": (ch.get("section_images") or {}).get(si)}
                          for si, title in enumerate(ch["sections"])]}
            for ch in outline["chapters"]
        ],
        "conclusion": conclusion,
        "references": references,
    }
