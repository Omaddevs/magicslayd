"""Maqolani Claude AI orqali yozadi.

1) Reja (asosiy model): sarlavha, annotatsiya va kalit so'zlar (ilmiy/sharh), bo'limlar — har biri uchun maqsad,
   hajm ulushi, kerak bo'lsa jadval (faqat sifat taqqoslash, o'ylab topilgan raqamlarsiz) va rasm kerakmi-yo'qmi.
2) Bo'limlar parallel yoziladi (tez model) — so'zlar soni hajmga qarab taqsimlanadi.
3) Manbalar — faqat OpenAlex/Crossref'dagi haqiqiy ishlar (diploma/sources.py); AI ulardan mavzuga moslarini tanlaydi,
   o'zi manba o'ylab topmaydi. Topilmasa — foydalanuvchiga ochiq aytiladi.
4) Rasmlar — faqat AI «kerak» degan bo'limlarga, haqiqiy fotolar va har biri AI ko'zi bilan tekshiriladi
   (presentation/ai.py → photo_checker). Sun'iy (AI chizgan) rasm ilmiy dalil sifatida ishlatilmaydi."""
import logging
import re

from config import AI_MODEL_WRITER
from diploma.sources import find_sources, format_source
from presentation.ai import LANGUAGE_PROMPT, GenerationError, ask_json, clean, photo_checker, run_all
from presentation.images import find_images

from articles.model import LABELS, normalize

TYPE_PROMPT = {
    "general": (
        "a GENERAL article for a broad audience: clear, fluent and easy to read. Structure: an introduction, "
        "a main part split into meaningful sections with headings (and subheadings where useful), and a conclusion."
    ),
    "scientific": (
        "a SCIENTIFIC (academic) article following journal conventions. Typical sections: Introduction; "
        "Literature review (state of research); Methodology; Results and analysis; Discussion; Conclusion. "
        "Adapt the set of sections to the topic — not every section is mandatory. Formal academic style, precise "
        "terminology, cautious claims."
    ),
    "analytical": (
        "an ANALYTICAL article: examine the problem in depth — the problem and its causes, consequences, evidence and "
        "examples, comparison of different viewpoints, proposed solutions and a final conclusion."
    ),
    "journalistic": (
        "a JOURNALISTIC (publicistic) article on a socially relevant topic: a catchy, interesting headline, a vivid "
        "and persuasive style, real-life examples and well-grounded opinions, and a meaningful ending."
    ),
    "review": (
        "a REVIEW article: survey existing research on the topic — summarize scientific views, compare approaches "
        "and findings, show similarities and differences, identify research gaps, and finish with a conclusion."
    ),
}
STYLE_PROMPT = {"auto": "", "academic": "Use a formal academic style.", "simple": "Use simple, plain language."}

SYSTEM = """You write high-quality articles for students, teachers and researchers in Uzbekistan.
Write with real substance, logical flow, correct grammar and spelling. Never repeat the same ideas or sentences.
Honesty rules (very important):
- Never invent statistics, percentages, survey results, dates, quotations, authors or studies.
- Do not cite specific papers or authors in the text; references are added separately from a real database.
- If a figure would be needed, describe the trend qualitatively instead of making up numbers.
No markdown headings, no emoji. Write every text in the requested language only — do not mix languages."""

_TEXTS = {"type": "array", "items": {"type": "string"}}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "abstract": {"type": "string"},
        "keywords": _TEXTS,
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "goal": {"type": "string"},
                    "share": {"type": "integer"},
                    "subheadings": _TEXTS,
                    "table": {
                        "type": "object",
                        "properties": {"use": {"type": "boolean"}, "caption": {"type": "string"},
                                       "columns": _TEXTS, "rows": {"type": "array", "items": _TEXTS}},
                        "required": ["use", "caption", "columns", "rows"],
                        "additionalProperties": False,
                    },
                    "image": {
                        "type": "object",
                        "properties": {"use": {"type": "boolean"}, "query": {"type": "string"},
                                       "caption": {"type": "string"}},
                        "required": ["use", "query", "caption"],
                        "additionalProperties": False,
                    },
                },
                "required": ["heading", "goal", "share", "subheadings", "table", "image"],
                "additionalProperties": False,
            },
        },
        "source_queries": _TEXTS,
    },
    "required": ["title", "abstract", "keywords", "sections", "source_queries"],
    "additionalProperties": False,
}
SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"kind": {"type": "string", "enum": ["p", "ul", "ol", "h3"]},
                               "text": {"type": "string"}, "items": _TEXTS},
                "required": ["kind", "text", "items"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["blocks"],
    "additionalProperties": False,
}
PICK_SCHEMA = {
    "type": "object",
    "properties": {"picked": {"type": "array", "items": {"type": "integer"}}},
    "required": ["picked"],
    "additionalProperties": False,
}

REFERENCES = {"scientific": (6, 12), "review": (10, 18), "analytical": (4, 8)}  # (kamida qidiriladi, ko'pi bilan)
# Bitta xatboshining amaldagi o'rtacha hajmi (85-110 so'z deb so'raladi; o'zbek va rus so'zlari uzunroq —
# model kamroq so'z yozadi). O'lchangan: uz ~80, ru ~85, en ~105
PARAGRAPH_WORDS = {"uz": 80, "ru": 85, "en": 105}


def sections_count(words):
    return max(3, min(9, round(words / 280)))


def images_cap(words):
    """Rasm ko'pi bilan: qisqa maqolaga 1, o'rtachaga 2, kengaytirilganga 3, juda kattasiga 4."""
    return 1 if words <= 800 else 2 if words <= 1700 else 3 if words <= 3200 else 4


def head(p):
    extra = []
    if p.get("purpose"):
        extra.append(f"Purpose of the article (from the user): {p['purpose']}")
    if p.get("notes"):
        extra.append(f"Additional requirements from the user (follow them unless they break the honesty rules): "
                     f"{p['notes']}")
    if STYLE_PROMPT.get(p.get("style")):
        extra.append(STYLE_PROMPT[p["style"]])
    return (f"Topic: {p['topic']}\nLanguage of all texts: {LANGUAGE_PROMPT[p['lang']]}\n"
            f"The text is {TYPE_PROMPT[p['type']]}\n" + "".join(f"{line}\n" for line in extra) + "\n")


def texts(values):
    return [clean(v) for v in values or [] if clean(v)]


# ===== 1. Reja =====
async def make_plan(p, words):
    count = sections_count(words)
    academic = p["type"] in ("scientific", "review")
    prompt = head(p) + (
        f"Plan the article (about {words} words in total):\n"
        "- `title`: a polished article title in the article language\n"
        f"- `abstract`: {'a 70-120 word abstract' if academic else 'empty string'}\n"
        f"- `keywords`: {'5-7 keywords' if academic else 'empty list'}\n"
        f"- `sections`: {count - 1}-{count + 1} sections in logical order (the first introduces, the last concludes); "
        "each with `heading`, `goal` (one sentence: what this section covers), `share` (percent of the total words, "
        "all shares sum to 100), `subheadings` (0-3, only when a section is long enough), "
        "`table` — use=true only if a compact table really helps (comparison of approaches, types, features, "
        "pros/cons); 2-5 columns, 2-6 rows, short QUALITATIVE cells, NEVER invented numbers or statistics; "
        "otherwise use=false with empty fields; "
        "`image` — use=true only if a real photograph would genuinely help understanding (a concrete object, place, "
        "process or tool), with `query` — 2-4 ENGLISH words for a stock photo search, main subject first, "
        f"concrete and photographable, and a short `caption` in the article language; at most {images_cap(words)} "
        "images in the whole article, none for abstract ideas\n"
        "- `source_queries`: 2-4 short ENGLISH search queries to find real scholarly works on the topic"
        + (" (important)" if p["type"] in REFERENCES else " (may be empty)")
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, PLAN_SCHEMA, max_tokens=6000)
        sections = [s for s in (data or {}).get("sections") or [] if clean(s.get("heading"))]
        if len(sections) >= 2:
            total = sum(max(1, int(s.get("share") or 0)) for s in sections) or 1
            # Annotatsiya (~100 so'z), ro'yxat va jadvallar ham hajmga qo'shiladi — bo'limlar shuncha kamroq
            budget = (words - (100 if academic else 0)) * 0.92
            for s in sections:
                s["words"] = max(60, round(budget * max(1, int(s.get("share") or 0)) / total))
            return {
                "title": clean(data.get("title")) or p["topic"],
                "abstract": clean(data.get("abstract")) if academic else "",
                "keywords": texts(data.get("keywords"))[:8] if academic else [],
                "sections": sections,
                "source_queries": texts(data.get("source_queries"))[:4],
            }
        logging.warning("Maqola rejasi noto'g'ri qaytdi")
    raise GenerationError("Maqola rejasini tuzib bo'lmadi. Iltimos, qayta urinib ko'ring.")


def plan_text(plan):
    return "\n".join(f"{i}. {s['heading']} — {clean(s.get('goal'))}" for i, s in enumerate(plan["sections"], 1))


# ===== 2. Bo'limlar matni =====
BOLD = re.compile(r"\*\*(.+?)\*\*")


def runs_of(text):
    """«**muhim atama**» belgilari qalin matnga aylanadi (AI kalit atamalarni ozgina ajratadi)."""
    runs, last = [], 0
    for match in BOLD.finditer(text):
        if match.start() > last:
            runs.append({"text": text[last:match.start()]})
        runs.append({"text": match.group(1), "b": 1})
        last = match.end()
    if last < len(text):
        runs.append({"text": text[last:]})
    return [r for r in runs if r["text"]]


async def write_section(p, plan, index):
    s = plan["sections"][index]
    # Hajm xatboshilar soni bilan boshqariladi — model «N so'z» dan ko'ra «N ta xatboshi» ni aniq bajaradi
    paragraphs = max(1, round(s["words"] / PARAGRAPH_WORDS.get(p["lang"], 100)))
    subs = texts(s.get("subheadings"))[:max(0, paragraphs - 1)]
    prompt = head(p) + (
        f"Article title: {plan['title']}\nFull plan:\n{plan_text(plan)}\n\n"
        f"Write section {index + 1} «{s['heading']}» — {clean(s.get('goal'))}\n"
        f"Length: EXACTLY {paragraphs} paragraph block(s) (`p`) of 85-110 words each — about {s['words']} words "
        "in total. Other sections are written separately — stay within this section.\n"
        + (f"Use these subheadings in order as `h3` blocks between the paragraphs: {'; '.join(subs)}.\n" if subs else "")
        + "Optionally, only where a list is natural, add ONE `ul` or `ol` block with `items` (2-5 short items) — it "
        "does not replace a paragraph. For `p` and `h3` put the text in `text` and leave `items` empty; for lists "
        "leave `text` empty. You may mark 1-3 key terms per section with **double asterisks**. "
        "Do not repeat the section heading."
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, SECTION_SCHEMA, max_tokens=6000, model=AI_MODEL_WRITER)
        blocks = []
        for b in (data or {}).get("blocks") or []:
            if b.get("kind") in ("ul", "ol"):
                items = [runs_of(i) for i in texts(b.get("items"))]
                if items:
                    blocks.append({"t": b["kind"], "items": items})
            elif clean(b.get("text")):
                kind = "h" if b.get("kind") == "h3" else "p"
                block = {"t": kind, "runs": runs_of(clean(b["text"]))}
                if kind == "h":
                    block.update(level=3, align="left")
                else:
                    block["align"] = "justify"
                blocks.append(block)
        if any(b["t"] == "p" for b in blocks):
            return blocks
        logging.warning("Maqola bo'limi yozilmadi: %s", s["heading"])
    raise GenerationError("Maqola matnini tayyorlab bo'lmadi. Iltimos, qayta urinib ko'ring.")


# ===== 3. Haqiqiy manbalar =====
async def pick_references(p, plan):
    """OpenAlex/Crossref'dagi haqiqiy ishlar: (formatlangan ro'yxat, ogohlantirish yoki "")."""
    if p["type"] not in REFERENCES:
        return [], ""
    low, high = REFERENCES[p["type"]]
    queries = plan["source_queries"] or [p["topic"]]
    candidates = await find_sources(queries, limit=max(20, high + 8))
    if not candidates:
        return [], "no_sources"
    listing = "\n".join(f"{i}. {c['title']} ({c['year']}) — {c.get('venue') or ''}" for i, c in enumerate(candidates))
    prompt = (f"Article topic: {p['topic']}\nArticle title: {plan['title']}\n\nCandidate works (real, from a "
              f"scholarly database):\n{listing}\n\nReturn `picked`: indices of the works that are clearly relevant "
              f"to the article topic, most relevant first, at most {high}. Skip unrelated ones.")
    try:
        data = await ask_json(SYSTEM, prompt, PICK_SCHEMA, max_tokens=1500, model=AI_MODEL_WRITER)
        picked = [i for i in dict.fromkeys((data or {}).get("picked") or []) if isinstance(i, int)
                  and 0 <= i < len(candidates)][:high]
    except GenerationError:
        picked = []
    if not picked:
        return [], "no_sources"
    refs = sorted((candidates[i] for i in picked), key=lambda c: (c["authors"].lower(), c["year"]))
    return [format_source(c, p["lang"]) for c in refs], ("few_sources" if len(refs) < low // 2 else "")


# ===== 4. Rasmlar =====
async def pick_images(p, plan, written):
    """AI «rasm kerak» degan bo'limlar uchun haqiqiy fotolar (AI tekshiruvidan o'tgan). {bo'lim: bytes}."""
    wanted = [i for i, s in enumerate(plan["sections"]) if (s.get("image") or {}).get("use")
              and clean((s.get("image") or {}).get("query"))][:images_cap(sum(s["words"] for s in plan["sections"]))]
    if not wanted:
        return {}
    outline = {"title": plan["title"]}
    targets = []
    for i in wanted:
        s = plan["sections"][i]
        first = next((b for b in written[i] if b["t"] == "p"), None)
        targets.append({"title": s["heading"], "text": "".join(r["text"] for r in first["runs"]) if first else "",
                        "items": [], "image_query": clean(s["image"]["query"]), "image_prompt": clean(s.get("goal"))})
    # Maqolada faqat HAQIQIY fotosurat: AI chizgan, 3D/CGI, gologramma yoki fantastik rasmlar rad etiladi
    real_only = ("This picture goes into an article, so it must be a REAL photograph: fits=false if it looks "
                 "AI-generated, a 3D/CGI render, a hologram, an illustration or fantasy imagery.")
    checks = [photo_checker(p["topic"], outline, t, real_only) for t in targets]
    found = await find_images([t["image_query"] for t in targets], set(), None, checks)
    return {i: image for i, image in zip(wanted, found) if image}


def runs(text, **marks):
    return [{"text": text, **marks}] if text else []


# ===== Yig'ish =====
async def generate_article(p, words):
    """p — {type, topic, lang, style, purpose, notes}. Natija: {title, blocks, images: {nom: bytes}, notice}."""
    plan = await make_plan(p, words)
    count = len(plan["sections"])
    *written, (references, notice) = await run_all(
        *(write_section(p, plan, i) for i in range(count)), pick_references(p, plan)
    )
    pictures = await pick_images(p, plan, written)

    labels = LABELS[p["lang"]]
    blocks, images, figure, table_no = [], {}, 0, 0
    if plan["abstract"]:
        blocks.append({"t": "h", "level": 2, "align": "left", "runs": runs(labels["abstract"])})
        blocks.append({"t": "p", "align": "justify", "runs": runs(plan["abstract"], i=1)})
    if plan["keywords"]:
        blocks.append({"t": "p", "align": "left",
                       "runs": runs(f"{labels['keywords']}: ", b=1) + runs(", ".join(plan["keywords"]), i=1)})
    for i, section in enumerate(plan["sections"]):
        blocks.append({"t": "h", "level": 2, "align": "left", "runs": runs(clean(section["heading"]))})
        body = written[i]
        first_p = next((k for k, b in enumerate(body) if b["t"] == "p"), 0)
        for k, block in enumerate(body):
            blocks.append(block)
            if k == first_p and i in pictures:
                figure += 1
                name = f"fig{figure}.jpg"
                images[name] = pictures[i]
                caption = clean(section["image"].get("caption")) or clean(section["heading"])
                blocks.append({"t": "img", "src": name, "width": 80, "align": "center",
                               "caption": f"{labels['figure'].format(n=figure)} {caption} ({labels['photo']})"})
        table = section.get("table") or {}
        columns, rows = texts(table.get("columns"))[:6], [texts(r) for r in table.get("rows") or []][:8]
        rows = [r[:len(columns)] + [""] * (len(columns) - len(r)) for r in rows if r]
        if table.get("use") and len(columns) >= 2 and rows:
            table_no += 1
            caption = clean(table.get("caption")) or clean(section["heading"])
            blocks.append({"t": "p", "align": "left",
                           "runs": runs(f"{labels['table'].format(n=table_no)} ", b=1) + runs(caption, i=1)})
            blocks.append({"t": "table", "head": True,
                           "rows": [[runs(c) for c in columns]] + [[runs(c) for c in r] for r in rows]})
    if references:
        blocks.append({"t": "h", "level": 2, "align": "left", "runs": runs(labels["references"])})
        blocks.append({"t": "ol", "items": [runs(ref) for ref in references]})
    return {"title": plan["title"], "blocks": normalize(blocks), "images": images, "notice": notice,
            "sources": len(references)}
