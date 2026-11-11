"""Diplom ishi matnini Claude orqali tayyorlaydi: metodika tahlili, reja, kirish, boblar, xulosa, tahrirlash.

Ilmiy halollik qoidalari (har bir so'rovda): statistika, so'rovnoma, respondentlar, tajriba natijalari, iqtibos,
qonun va manbalar O'YLAB TOPILMAYDI. Iqtibos faqat berilgan haqiqiy manbalar ro'yxatidan ([n]) olinadi.
Ma'lumot yetishmasa — metodika tasvirlanadi, misol ma'lumot esa aniq «namunaviy» deb belgilanadi.
Mavjud yordamchilar (presentation/ai.py: ask_json, run_all) faqat chaqiriladi — o'zgartirilmaydi."""
import logging
import re

from config import AI_MODEL, AI_MODEL_WRITER
from presentation.ai import LANGUAGE_PROMPT, GenerationError, ask_json, clean, run_all

WORDS_PER_PAGE = 280  # Times New Roman 14, 1.5 interval
PARAGRAPH_WORDS = 130
SERVICE_PAGES = 6  # titul, mundarija (2), adabiyotlar, ilovalar
CHUNK = 3  # bitta so'rovda nechta xatboshi yoziladi
MAX_SECTION_PARAGRAPHS = 18

FIELDS = {
    "it": "Information technology — the practical chapter designs a concrete technical solution: system "
          "architecture, algorithm, database or interface design, implementation steps and testing approach.",
    "economics": "Economics / finance / management — the practical chapter analyses indicators of a real "
                 "organisation or sector ONLY from the user's materials; otherwise it explains the calculation "
                 "methodology and labels any numbers as illustrative.",
    "pedagogy": "Pedagogy / education — the practical chapter develops lesson methodology, didactic materials, "
                "an experiment design and evaluation criteria (no invented experiment results).",
    "engineering": "Engineering — the practical chapter covers technical design, calculation methods, schemes and "
                   "technological solutions, with formulas explained.",
    "medicine": "Medicine / health — a scientific literature-based analysis within methodological norms; never "
                "give clinical claims without sources and never invent clinical data.",
    "law": "Law — analysis of legislation and practice; cite only real laws that are in the provided sources or "
           "that the user named; otherwise discuss principles without inventing article numbers.",
    "humanities": "Humanities / history / philology — source analysis, interpretation and comparison.",
    "natural": "Natural sciences — methods, models and analysis; no invented measurements.",
    "other": "Practical chapter with solutions and recommendations that fit the topic.",
}
SAMPLE_LABEL = {"uz": "namunaviy", "ru": "условный пример", "en": "illustrative example"}

INTRO_LABELS = {
    "uz": ["Mavzuning dolzarbligi", "Muammoning o'rganilganlik darajasi", "Tadqiqotning maqsadi",
           "Tadqiqotning vazifalari", "Tadqiqot obyekti", "Tadqiqot predmeti", "Tadqiqot metodlari",
           "Ishning nazariy ahamiyati", "Ishning amaliy ahamiyati", "Ishning tuzilishi"],
    "ru": ["Актуальность темы", "Степень изученности проблемы", "Цель исследования", "Задачи исследования",
           "Объект исследования", "Предмет исследования", "Методы исследования", "Теоретическая значимость работы",
           "Практическая значимость работы", "Структура работы"],
    "en": ["Relevance of the topic", "Degree of study of the problem", "Aim of the research", "Objectives of the research",
           "Object of the research", "Subject of the research", "Research methods", "Theoretical significance",
           "Practical significance", "Structure of the thesis"],
}

SYSTEM = """You write a graduation thesis (diplom ishi / bitiruv malakaviy ishi) for a university student in Uzbekistan.
Formal academic style: precise, coherent, logically connected, with real substance. No filler, no repeated sentences,
no markdown, no emoji, no bullet characters, no numbering inside titles (numbering is added automatically).

ACADEMIC INTEGRITY — strict rules:
- Never invent statistics, survey results, numbers of respondents, experiment results, measurements, quotations,
  laws, article numbers, organisations' internal data or sources.
- Cite ONLY works from the numbered source list given in the prompt, as [n] (several: [2, 5]); never cite anything else.
  Cite where a claim really relies on the literature; do not attach citations to your own reasoning.
- Use concrete figures only if they come from the user's materials (then name the material) or are widely known,
  stable facts. If data is needed but missing, describe how it should be collected and calculated, and mark any
  example data explicitly with the word given as SAMPLE LABEL.
- The text is a draft that the student will check and agree with the supervisor."""


def lang_of(project):
    lang = project["info"].get("lang") or "uz"
    return lang if lang in LANGUAGE_PROMPT else "uz"


def head(project):
    info = project["info"]
    lang = lang_of(project)
    lines = [
        f"Thesis topic: {info['topic']}",
        f"Language of all texts: {LANGUAGE_PROMPT[lang]}",
        f"SAMPLE LABEL: «{SAMPLE_LABEL.get(lang, 'namunaviy')}»",
    ]
    for key, label in (("direction", "Field of study"), ("specialty", "Specialty"), ("faculty", "Faculty"),
                       ("university", "University")):
        if info.get(key):
            lines.append(f"{label}: {info[key]}")
    if info.get("extra"):
        lines.append(f"Additional requirements from the student: {info['extra']}")
    return "\n".join(lines) + "\n"


def texts(values):
    return [clean(v) for v in values or [] if clean(v)]


def sources_text(project, limit=40):
    items = project.get("sources") or []
    if not items:
        return "Source list: (empty — do not cite anything, write without [n] markers)\n"
    lines = [f"[{s['n']}] {s['authors']}. {s['title']} ({s['year']})" + (f", {s['venue']}" if s.get("venue") else "")
             for s in items[:limit]]
    return "Numbered source list (cite ONLY these, as [n]):\n" + "\n".join(lines) + "\n"


def method_text(project):
    method = project.get("method") or {}
    if method.get("status") != "analyzed" or not method.get("found"):
        return "University methodology: not provided — follow common Uzbek university requirements.\n"
    lines = [f"- {f['label']}: {f['value']}" for f in method["found"][:30]]
    return "Requirements from the university methodology (follow them):\n" + "\n".join(lines) + "\n"


def plan_text(project):
    lines = []
    for i, chapter in enumerate(project["plan"]["chapters"], 1):
        lines.append(f"Chapter {i}. {chapter['title']}")
        lines += [f"  {i}.{j}. {s['title']}" for j, s in enumerate(chapter["sections"], 1)]
    return "\n".join(lines)


def strip_citations(paragraphs, project):
    """[n] faqat mavjud manbalarga ishora qilsin — boshqalari olib tashlanadi."""
    valid = {s["n"] for s in project.get("sources") or []}

    def fix(match):
        numbers = [int(n) for n in re.findall(r"\d+", match.group(0)) if int(n) in valid]
        return f"[{', '.join(map(str, numbers))}]" if numbers else ""

    return [re.sub(r"\s*\[\d+(?:\s*[,;–-]\s*\d+)*\]", lambda m: (" " + fix(m)) if fix(m) else "", p).strip()
            for p in paragraphs]


# ===== 1. Metodik qo'llanma tahlili =====
METHOD_KEYS = {
    "structure": "Tarkibi", "pages": "Hajmi (betlar)", "chapters": "Boblar soni", "sections": "Paragraflar soni",
    "font": "Shrift", "font_size": "Shrift o'lchami", "line_spacing": "Qatorlar oralig'i", "margins": "Sahifa chetlari",
    "intro": "Kirish talablari", "conclusion": "Xulosa talablari", "figures": "Rasmlar", "tables": "Jadvallar",
    "citations": "Iqtibos shakli", "references": "Adabiyotlar ro'yxati", "appendix": "Ilovalar", "other": "Boshqa talablar",
}
METHOD_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": list(METHOD_KEYS)},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["key", "value", "quote"],
                "additionalProperties": False,
            },
        },
        "numbers": {
            "type": "object",
            "properties": {k: {"type": "number"} for k in (
                "font_size", "line_spacing", "margin_left", "margin_right", "margin_top", "margin_bottom",
                "pages_min", "pages_max", "chapters", "sections_per_chapter", "min_sources")},
            "required": ["font_size", "line_spacing", "margin_left", "margin_right", "margin_top", "margin_bottom",
                         "pages_min", "pages_max", "chapters", "sections_per_chapter", "min_sources"],
            "additionalProperties": False,
        },
        "font_name": {"type": "string"},
    },
    "required": ["found", "numbers", "font_name"],
    "additionalProperties": False,
}
NUMBER_KEY = {"font_size": "font_size", "line_spacing": "line_spacing", "margin_left": "margins",
              "margin_right": "margins", "margin_top": "margins", "margin_bottom": "margins", "pages_min": "pages",
              "pages_max": "pages", "chapters": "chapters", "sections_per_chapter": "sections",
              "min_sources": "references"}


def _norm(text):
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


async def analyze_method(text):
    """Qo'llanmadan talablar. Har bir talab qo'llanmadagi aynan iqtibos bilan; iqtibos matnda topilmasa —
    talab tashlanadi (AI o'ylab topgan bo'lishi mumkin). Raqamlar ham faqat tasdiqlangan turdagi talab bo'lsa olinadi."""
    prompt = (
        "Below is a university methodology for writing graduation theses. Extract ONLY the requirements that are "
        "explicitly written in it. For every requirement give `key`, a short `value` in Uzbek, and `quote` — an "
        "exact fragment (5-25 words) copied from the text that states it. If something is not stated, do not "
        "include it. In `numbers` put the stated values (cm for margins, points for font size) and 0 for anything "
        "not stated. `font_name` — the stated font or an empty string.\n\nMETHODOLOGY:\n" + text
    )
    data = await ask_json(SYSTEM, prompt, METHOD_SCHEMA, max_tokens=6000, model=AI_MODEL)
    if not data:
        raise GenerationError("Metodik qo'llanmani tahlil qilib bo'lmadi. Qayta urinib ko'ring.")
    haystack = _norm(text)
    found = []
    for item in data.get("found") or []:
        quote = clean(item.get("quote"))
        words = _norm(quote).split()
        # Iqtibosning kamida 5 so'zli bo'lagi qo'llanmada aynan bo'lishi shart
        ok = len(words) >= 3 and any(" ".join(words[i:i + 5]) in haystack for i in range(max(1, len(words) - 4)))
        if ok and clean(item.get("value")):
            found.append({"key": item["key"], "label": METHOD_KEYS[item["key"]], "value": clean(item["value"])[:300],
                          "quote": quote[:300]})
        else:
            logging.info("Metodikadan tasdiqlanmagan talab tashlandi: %s", item.get("key"))
    keys = {f["key"] for f in found}
    rules = {}
    for name, value in (data.get("numbers") or {}).items():
        if value and NUMBER_KEY.get(name) in keys:
            rules[name] = value
    if clean(data.get("font_name")) and "font" in keys:
        rules["font_name"] = clean(data["font_name"])[:60]
    return {"found": found, "rules": rules}


# ===== 2. Reja =====
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "enum": list(FIELDS)},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "sections": {"type": "array", "items": {"type": "string"}}},
                "required": ["title", "sections"],
                "additionalProperties": False,
            },
        },
        "search_queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["field", "chapters", "search_queries"],
    "additionalProperties": False,
}


def plan_shape(project):
    """Boblar va paragraflar soni: metodikada yozilgan bo'lsa — o'sha, aks holda hajmga qarab."""
    rules = (project.get("method") or {}).get("rules") or {}
    pages = int(project["info"].get("pages") or 60)
    chapters = int(rules.get("chapters") or 3)
    sections = int(rules.get("sections_per_chapter") or (2 if pages < 50 else 3 if pages < 110 else 4))
    return max(2, min(5, chapters)), max(2, min(5, sections))


async def make_plan(project, materials=""):
    chapters, sections = plan_shape(project)
    prompt = head(project) + method_text(project) + (
        f"\nMaterials uploaded by the student (excerpt):\n{materials[:4000]}\n" if materials else ""
    ) + (
        f"\nCreate the thesis plan: exactly {chapters} chapters, each with exactly {sections} section titles.\n"
        "Analyse the topic deeply: the plan must be specific to THIS topic, not generic. Typical logic: chapter 1 — "
        "theoretical foundations; chapter 2 — analysis / research of the current state; the last chapter — practical "
        "part, proposals and solutions (adapt to the field and to the methodology). Section titles must not overlap.\n"
        "`field` — the field of the thesis. `search_queries` — 6-8 short ENGLISH queries (3-6 words) for finding real "
        "scientific papers on the topic in OpenAlex (cover every chapter; for local topics include the country, "
        "e.g. 'Uzbekistan')."
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, PLAN_SCHEMA, max_tokens=4000, model=AI_MODEL)
        result = [{"title": clean(c.get("title")), "sections": [{"title": t} for t in texts(c.get("sections"))[:sections]]}
                  for c in (data or {}).get("chapters") or [] if clean(c.get("title"))][:chapters]
        if len(result) == chapters and all(len(c["sections"]) == sections for c in result):
            return {"field": data.get("field") or "other", "chapters": result,
                    "queries": texts(data.get("search_queries"))[:8]}
        logging.warning("AI diplom rejasini noto'g'ri qaytardi")
    raise GenerationError("Rejani tuzib bo'lmadi. Iltimos, qayta urinib ko'ring.")


# ===== Hajm taqsimoti =====
def budget(project):
    """Har bir qism uchun xatboshilar soni: kirish, har bir bo'lim, bob xulosasi, xulosa."""
    pages = int(project["info"].get("pages") or 60)
    total = max(20, pages - SERVICE_PAGES) * WORDS_PER_PAGE
    chapters = project["plan"]["chapters"]
    body = total * 0.86
    per_chapter = body / max(1, len(chapters))
    return {
        "intro": max(6, round(total * 0.07 / PARAGRAPH_WORDS)),
        "conclusion": max(3, round(total * 0.05 / PARAGRAPH_WORDS)),
        "sections": [[min(MAX_SECTION_PARAGRAPHS, max(2, round(per_chapter * 0.92 / len(c["sections"]) / PARAGRAPH_WORDS)))
                      for _ in c["sections"]] for c in chapters],
    }


# ===== 3. Kirish =====
INTRO_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"index": {"type": "integer"}, "paragraphs": {"type": "array", "items": {"type": "string"}}},
        "required": ["index", "paragraphs"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}


async def write_intro(project):
    lang = lang_of(project)
    labels = INTRO_LABELS[lang]
    total = budget(project)["intro"]
    prompt = head(project) + method_text(project) + sources_text(project) + (
        f"\nThesis plan:\n{plan_text(project)}\n\n"
        f"Write the INTRODUCTION (about {total} paragraphs of 80-150 words in total) as `items`, one per index:\n"
        + "\n".join(f"{i}. {label}" for i, label in enumerate(labels, 1)) +
        "\nThe relevance part gets 2-3 paragraphs; the degree-of-study part reviews the cited literature from the list "
        "(2 paragraphs); the objectives correspond to the plan sections; object and subject are one short paragraph "
        "each; the structure part describes the real chapters of the plan. All parts must be consistent with each "
        "other. Do not repeat the label inside the text."
    )
    data = await ask_json(SYSTEM, prompt, INTRO_SCHEMA, max_tokens=8000, model=AI_MODEL)
    by_index = {item.get("index"): texts(item.get("paragraphs")) for item in (data or {}).get("items") or []}
    items = [{"label": label, "paragraphs": strip_citations(by_index.get(i) or [], project)}
             for i, label in enumerate(labels, 1)]
    if sum(1 for item in items if item["paragraphs"]) < 8:
        raise GenerationError("Kirish qismini tayyorlab bo'lmadi. Iltimos, qayta urinib ko'ring.")
    return [item for item in items if item["paragraphs"]]


# ===== 4. Boblar =====
PARAGRAPHS_SCHEMA = {
    "type": "object",
    "properties": {"paragraphs": {"type": "array", "items": {"type": "string"}}},
    "required": ["paragraphs"],
    "additionalProperties": False,
}


def chapter_context(project, index):
    """Avvalgi boblarning xulosalari — boblar orasidagi mantiqiy bog'liqlik uchun."""
    lines = []
    for i, chapter in enumerate(project["chapters"][:index], 1):
        if chapter.get("summary"):
            lines.append(f"Summary of chapter {i} «{chapter['title']}»: " + " ".join(chapter["summary"])[:900])
    return ("\n".join(lines) + "\n") if lines else ""


async def write_part(project, ci, si, first, count, total, materials):
    chapter = project["plan"]["chapters"][ci]
    section = chapter["sections"][si]
    practical = ci == len(project["plan"]["chapters"]) - 1
    field = project["plan"].get("field") or "other"
    position = ("the whole section" if count == total else
                f"paragraphs {first}-{first + count - 1} of {total} of this section (others are written separately: "
                "opening paragraphs introduce, middle ones develop with arguments and examples, final ones conclude)")
    prompt = head(project) + method_text(project) + sources_text(project) + chapter_context(project, ci) + (
        f"\nField guidance: {FIELDS[field]}\n" if practical else ""
    ) + (
        f"\nMaterials uploaded by the student (use them as the factual basis; name the material when you use its data):\n"
        f"{materials[:6000]}\n" if materials and ci > 0 else ""
    ) + (
        f"\nThesis plan:\n{plan_text(project)}\n\n"
        f"Write section {ci + 1}.{si + 1} «{section['title']}» of chapter {ci + 1} «{chapter['title']}».\n"
        f"Write {position}. `paragraphs`: exactly {count} paragraphs of 110-160 words. Stay within this section's "
        "scope, give concrete explanations and examples, distinguish theory from practice."
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, PARAGRAPHS_SCHEMA, max_tokens=7000, model=AI_MODEL_WRITER)
        written = texts((data or {}).get("paragraphs"))
        if written:
            return strip_citations(written[:count], project)
        logging.warning("AI diplom bo'limini yozmadi: %s.%s", ci + 1, si + 1)
    raise GenerationError("Bobni yozib bo'lmadi. Iltimos, qayta urinib ko'ring.")


async def write_section(project, ci, si, total, materials):
    parts = await run_all(*(write_part(project, ci, si, first + 1, min(CHUNK, total - first), total, materials)
                            for first in range(0, total, CHUNK)))
    return [p for part in parts for p in part]


VISUALS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "visuals": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["scheme", "illustration", "table"]},
                "caption": {"type": "string"},
                "section": {"type": "integer"},
                "paragraph": {"type": "integer"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "image_prompt": {"type": "string"},
                "image_query": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            },
            "required": ["kind", "caption", "section", "paragraph", "steps", "image_prompt", "image_query", "columns", "rows"],
            "additionalProperties": False,
        }},
        "topic_query": {"type": "string"},
    },
    "required": ["summary", "visuals", "topic_query"],
    "additionalProperties": False,
}


def visuals_plan(project):
    """Bitta bobga vizual materiallar soni va ulardan nechtasi rasm (illyustratsiya) bo'lishi — hajmga qarab.
    60 betlik, 3 bobli ishda: bobga 4 ta vizual, kamida 2 tasi rasm (jami ~12 vizual, ~6+ rasm)."""
    pages = int(project["info"].get("pages") or 60)
    chapters = max(1, len(project["plan"]["chapters"]))
    total = max(3, min(7, round(pages / chapters / 5)))
    return total, max(2, (total + 1) // 2)


async def chapter_extras(project, ci, sections):
    """Bob xulosasi va vizual materiallar rejasi (sxema / illyustratsiya / jadval)."""
    chapter = project["plan"]["chapters"][ci]
    total, pictures = visuals_plan(project)
    outline = []
    for si, (section, paragraphs) in enumerate(zip(chapter["sections"], sections), 1):
        outline.append(f"Section {ci + 1}.{si} «{section['title']}» ({len(paragraphs)} paragraphs):")
        outline += [f"  p{pi}: {p[:220]}" for pi, p in enumerate(paragraphs, 1)]
    prompt = head(project) + (
        f"\nChapter {ci + 1} «{chapter['title']}» (beginning of every paragraph):\n" + "\n".join(outline)[:14000] +
        "\n\n`summary`: the chapter conclusion — 1-2 paragraphs (80-140 words) summarising ONLY what the chapter says."
        f"\n`visuals`: {total} visual materials that explain the content, spread evenly over the sections "
        "(different sections and paragraphs, never two in a row), each attached after "
        "`section` (1-based) and `paragraph` (1-based) where it is discussed. Kinds:\n"
        "- scheme: a process, structure or classification as 3-6 short boxes in `steps` (each at most 6 words);\n"
        "- illustration: a realistic picture of the CONCRETE things the paragraph discusses (equipment, technology, "
        "place, process in action, people at work); `image_prompt` — one detailed English sentence naming the "
        "concrete objects, the setting (country / region if relevant to the topic) and what is happening; never "
        "abstract concepts, charts or text; `image_query` — 2-4 ENGLISH words to find a real stock photo of the "
        "same subject (main subject first, concrete and photographable, e.g. \"wheat harvest combine\"). "
        f"At least {pictures} of the visuals in this chapter MUST be illustrations, each showing a different subject;\n"
        "- table: a comparison or classification with 2-5 `columns` and 2-7 `rows` of short QUALITATIVE text. "
        "NEVER put invented numbers or statistics in tables.\n"
        "`caption` — short title in the thesis language. Unused fields: empty.\n"
        "`topic_query` — 2-4 ENGLISH words for a stock photo of this chapter's overall subject (used if a specific "
        "photo is not found)."
    )
    data = await ask_json(SYSTEM, prompt, VISUALS_SCHEMA, max_tokens=7000, model=AI_MODEL)
    topic_query = clean((data or {}).get("topic_query"))
    summary = texts((data or {}).get("summary"))[:2]
    visuals = []
    for raw in (data or {}).get("visuals") or []:
        si, pi = int(raw.get("section") or 1) - 1, int(raw.get("paragraph") or 1) - 1
        if not (0 <= si < len(sections)) or not sections[si]:
            continue
        pi = max(0, min(pi, len(sections[si]) - 1))
        item = {"kind": raw["kind"], "caption": clean(raw.get("caption"))[:200], "section": si, "paragraph": pi}
        if raw["kind"] == "scheme":
            item["steps"] = [s[:60] for s in texts(raw.get("steps"))][:6]
            if len(item["steps"]) < 3:
                continue
        elif raw["kind"] == "illustration":
            item["image_prompt"] = clean(raw.get("image_prompt"))
            if not item["image_prompt"]:
                continue
            # AI chiza olmasa — shu so'rov bilan fotobazadan (diploma/figures.py → illustrate)
            item["image_query"] = clean(raw.get("image_query"))[:80]
            item["fallback_query"] = topic_query[:80]
        else:
            columns = texts(raw.get("columns"))[:5]
            rows = [[clean(c)[:200] for c in row][:len(columns)] for row in raw.get("rows") or []][:7]
            rows = [row + [""] * (len(columns) - len(row)) for row in rows if any(row)]
            # Jadvalda raqamli «statistika» bo'lmasin — o'ylab topilgan bo'lishi mumkin
            if len(columns) < 2 or len(rows) < 2 or any(re.search(r"\d+[.,]?\d*\s*%", c) for row in rows for c in row):
                continue
            item.update(columns=columns, rows=rows)
        if item["caption"]:
            visuals.append(item)
    return summary, visuals[:total + 1]


async def write_chapter(project, ci, materials=""):
    """(sections — xatboshilar ro'yxatlari, summary, visuals)."""
    counts = budget(project)["sections"][ci]
    sections = await run_all(*(write_section(project, ci, si, n, materials) for si, n in enumerate(counts)))
    summary, visuals = await chapter_extras(project, ci, sections)
    return sections, summary, visuals


# ===== 5. Xulosa =====
async def write_conclusion(project):
    total = budget(project)["conclusion"]
    tasks = next((item["paragraphs"] for item in project["intro"]["items"]
                  if item["label"] in (INTRO_LABELS["uz"][3], INTRO_LABELS["ru"][3], INTRO_LABELS["en"][3])), [])
    summaries = "\n".join(f"Chapter {i}: " + " ".join(c.get("summary") or [])
                          for i, c in enumerate(project["chapters"], 1))
    prompt = head(project) + (
        f"\nObjectives stated in the introduction:\n{' '.join(tasks)[:2500]}\n\nChapter conclusions:\n{summaries[:6000]}\n\n"
        f"Write the CONCLUSION: exactly {total} paragraphs of 100-150 words — main results of the research, identified "
        "problems, proposed solutions, practical recommendations, and how the aim and objectives were achieved. "
        "Use ONLY results that appear in the chapter conclusions above — no new results, numbers or claims."
    )
    data = await ask_json(SYSTEM, prompt, PARAGRAPHS_SCHEMA, max_tokens=6000, model=AI_MODEL)
    paragraphs = texts((data or {}).get("paragraphs"))
    if not paragraphs:
        raise GenerationError("Xulosani yozib bo'lmadi. Iltimos, qayta urinib ko'ring.")
    return strip_citations(paragraphs[:total + 1], project)


# ===== 6. Tahrirlash amallari =====
OPS = {
    "expand": "Expand the paragraph to about 1.5x length with more explanation and an example; keep the meaning.",
    "shorten": "Shorten the paragraph to about 60% of its length, keeping the key ideas.",
    "fix": "Fix spelling, grammar and punctuation only; do not change the content or style.",
    "style": "Improve the academic style and clarity; keep the content and all [n] citations.",
    "regenerate": "Rewrite the paragraph from scratch with the same role in the section, without repeating its wording.",
}
ONE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


async def rewrite(project, text, op, where):
    prompt = head(project) + sources_text(project) + (
        f"\nThe paragraph belongs to: {where}\n\nPARAGRAPH:\n{text}\n\nTask: {OPS[op]} "
        "Return the new paragraph in `text`."
    )
    data = await ask_json(SYSTEM, prompt, ONE_SCHEMA, max_tokens=3000, model=AI_MODEL_WRITER if op == "fix" else AI_MODEL)
    result = clean((data or {}).get("text"))
    if not result:
        raise GenerationError("Matnni o'zgartirib bo'lmadi. Qayta urinib ko'ring.")
    return strip_citations([result], project)[0]
