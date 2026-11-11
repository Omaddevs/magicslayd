"""Dissertatsiya matnini Claude orqali tayyorlaydi: mavzu takliflari, metodika tahlili, reja, kirish, boblar
(vizual materiallar rejasi bilan), xulosa, annotatsiya, mazmuniy muvofiqlik tekshiruvi, tahrirlash amallari.

Ilmiy halollik qoidalari har bir so'rovda: statistika, respondentlar, tajriba natijalari, joriy etish dalolatnomalari,
aprobatsiya, nashrlar, patentlar va manbalar O'YLAB TOPILMAYDI. Iqtibos — faqat berilgan haqiqiy manbalardan ([n]).
Raqamlar — faqat foydalanuvchi materiallaridan (ular Python'da hisoblanadi) yoki aniq «namunaviy» belgisi bilan.
Ilmiy yangilik va ishonchlilik — natija hali yo'q bo'lsa, «taklif etiladi / asoslanadi» shaklida (tasdiqlangan deb emas)."""
import logging
import re

from config import AI_MODEL, AI_MODEL_WRITER, DISS_TYPES
from presentation.ai import LANGUAGE_PROMPT, GenerationError, ask_json, clean, run_all

WORDS_PER_PAGE = 280
PARAGRAPH_WORDS = 140
CHUNK = 3
MAX_SECTION_PARAGRAPHS = 30

KIND_PROMPT = {
    "master": "a MASTER'S dissertation: thorough literature review, analysis of the current state, well-argued "
              "practical recommendations; moderate theoretical contribution.",
    "phd": "a PhD (Doctor of Philosophy) dissertation in the style required by the Higher Attestation Commission of "
           "Uzbekistan: deep theoretical analysis, the author's own methodological approach, clearly formulated "
           "scientific novelty and practical results that can be verified.",
    "dsc": "a DSc (Doctor of Science) dissertation: a conceptual contribution — a new theory, model or concept, "
           "broad generalisation of the field, strong methodological apparatus.",
    "other": "a scientific research work with a clear aim, methods, analysis and conclusions.",
}
FIELDS = {
    "it": "Information technology: design a concrete technical solution — architecture, algorithms, data model, "
          "implementation and testing methodology.",
    "economics": "Economics / management: analyse indicators ONLY from the user's data; otherwise describe the "
                 "calculation methodology and label example numbers as illustrative.",
    "pedagogy": "Pedagogy: methodology, didactic model, experiment design and evaluation criteria (results only from "
                "the user's data).",
    "engineering": "Engineering: technical design, calculation methods, schemes, formulas explained.",
    "medicine": "Medicine: literature-based scientific analysis within ethical and methodological norms; never invent "
                "clinical data.",
    "law": "Law: analysis of legislation and practice; cite only real acts present in the sources or named by the user.",
    "humanities": "Humanities: source analysis, interpretation, comparison.",
    "natural": "Natural sciences: methods, models, analysis; no invented measurements.",
    "other": "Practical chapter with well-grounded solutions and recommendations.",
}
SAMPLE_LABEL = {"uz": "namunaviy", "ru": "условный пример", "en": "illustrative example"}
INTRO_LABELS = {
    "uz": ["Mavzuning dolzarbligi va zarurati", "Muammoning o'rganilganlik darajasi", "Tadqiqotning maqsadi",
           "Tadqiqotning vazifalari", "Tadqiqotning obyekti", "Tadqiqotning predmeti", "Tadqiqot metodlari",
           "Tadqiqotning ilmiy yangiligi", "Tadqiqotning nazariy ahamiyati", "Tadqiqotning amaliy ahamiyati",
           "Tadqiqot natijalarining ishonchliligi", "Dissertatsiyaning tuzilishi va hajmi"],
    "ru": ["Актуальность и востребованность темы", "Степень изученности проблемы", "Цель исследования",
           "Задачи исследования", "Объект исследования", "Предмет исследования", "Методы исследования",
           "Научная новизна исследования", "Теоретическая значимость", "Практическая значимость",
           "Достоверность результатов исследования", "Структура и объём диссертации"],
    "en": ["Relevance of the topic", "Degree of study of the problem", "Aim of the research", "Objectives of the research",
           "Object of the research", "Subject of the research", "Research methods", "Scientific novelty",
           "Theoretical significance", "Practical significance", "Reliability of the results",
           "Structure and volume of the dissertation"],
}

SYSTEM = """You write a dissertation for a researcher in Uzbekistan (master's, PhD or DSc level).
Rigorous academic style: precise terminology, coherent argumentation, logical links between parts, real substance.
No filler, no repeated sentences, no markdown, no emoji, no bullets, no numbering inside titles.

ACADEMIC INTEGRITY — strict rules:
- Never invent statistics, survey results, numbers of respondents, experiments, measurements, implementation acts,
  approbation at conferences, publications, patents, quotations, laws, article numbers or sources.
- Cite ONLY works from the numbered source list in the prompt, as [n] (several: [2, 5]); nothing else.
- Concrete numbers only from the user's materials (name the material) or widely known stable facts. If data is
  missing, describe how it will be collected and analysed, and mark example data with the SAMPLE LABEL word.
- Scientific novelty, results and reliability: if the researcher has not provided results, formulate them as the
  contributions this work proposes and substantiates — never as already confirmed, implemented or approbated.
- The text is a draft for the researcher to verify and agree with the supervisor."""


def lang_of(project):
    lang = project["info"].get("lang") or "uz"
    return lang if lang in LANGUAGE_PROMPT else "uz"


def head(project):
    info, lang = project["info"], lang_of(project)
    lines = [
        f"Dissertation type: {KIND_PROMPT.get(project.get('kind') or 'other', KIND_PROMPT['other'])}",
        f"Topic: {info['topic']}",
        f"Language of all texts: {LANGUAGE_PROMPT[lang]}",
        f"SAMPLE LABEL: «{SAMPLE_LABEL.get(lang, 'namunaviy')}»",
    ]
    for key, label in (("direction", "Research field"), ("specialty", "Specialty"), ("specialty_code", "Specialty code"),
                       ("degree", "Degree sought"), ("problem", "Research problem stated by the researcher"),
                       ("existing", "What the researcher already has (data, results, publications)"),
                       ("extra", "Additional requirements")):
        if info.get(key):
            lines.append(f"{label}: {info[key]}")
    return "\n".join(lines) + "\n"


def texts(values):
    return [clean(v) for v in values or [] if clean(v)]


def sources_text(project, limit=60):
    items = project.get("sources") or []
    if not items:
        return "Source list: (empty — do not cite anything)\n"
    lines = [f"[{s['n']}] {s['authors']}. {s['title']} ({s['year']})" + (f", {s['venue']}" if s.get("venue") else "")
             for s in items[:limit]]
    return "Numbered source list (cite ONLY these, as [n]):\n" + "\n".join(lines) + "\n"


def method_text(project):
    method = project.get("method") or {}
    if method.get("status") != "analyzed" or not method.get("found"):
        return "Methodology of the institution: not provided — follow common requirements for this dissertation type.\n"
    return "Requirements from the institution's methodology (follow them):\n" + "\n".join(
        f"- {f['label']}: {f['value']}" for f in method["found"][:30]) + "\n"


def plan_text(project):
    lines = []
    for i, chapter in enumerate(project["plan"]["chapters"], 1):
        lines.append(f"Chapter {i}. {chapter['title']}")
        lines += [f"  {i}.{j}. {s['title']}" for j, s in enumerate(chapter["sections"], 1)]
    return "\n".join(lines)


def strip_citations(paragraphs, project):
    valid = {s["n"] for s in project.get("sources") or []}

    def fix(match):
        numbers = [int(n) for n in re.findall(r"\d+", match.group(0)) if int(n) in valid]
        return f" [{', '.join(map(str, numbers))}]" if numbers else ""

    return [re.sub(r"\s*\[\d+(?:\s*[,;–-]\s*\d+)*\]", fix, p).strip() for p in paragraphs]


# ===== Mavzu takliflari =====
TOPICS_SCHEMA = {
    "type": "object",
    "properties": {"topics": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "why": {"type": "string"}},
        "required": ["title", "why"], "additionalProperties": False}}},
    "required": ["topics"], "additionalProperties": False,
}


async def suggest_topics(project):
    prompt = head(project) + (
        "\nThe researcher does not have an exact topic yet. Suggest 5 precise, researchable dissertation topics for "
        "this field and type (current, specific, with a clear object and subject; for local relevance — Uzbekistan). "
        "`why` — one sentence why the topic is relevant. Both in the dissertation language."
    )
    data = await ask_json(SYSTEM, prompt, TOPICS_SCHEMA, max_tokens=3000, model=AI_MODEL)
    topics = [{"title": clean(t.get("title"))[:300], "why": clean(t.get("why"))[:400]}
              for t in (data or {}).get("topics") or [] if clean(t.get("title"))]
    if not topics:
        raise GenerationError("Mavzu takliflarini tayyorlab bo'lmadi. Qayta urinib ko'ring.")
    return topics[:5]


# ===== Metodika tahlili =====
METHOD_KEYS = {
    "structure": "Tuzilishi", "pages": "Hajmi (betlar)", "chapters": "Boblar soni", "sections": "Paragraflar",
    "headings": "Sarlavhalar", "font": "Shrift", "font_size": "Shrift o'lchami", "line_spacing": "Qatorlar oralig'i",
    "margins": "Sahifa chetlari", "annotation": "Annotatsiya", "intro": "Kirish talablari",
    "conclusion": "Xulosa talablari", "references": "Adabiyotlar", "citations": "Iqtibos shakli",
    "figures": "Rasmlar", "tables": "Jadvallar", "appendix": "Ilovalar", "other": "Boshqa talablar",
}
NUMBER_KEY = {"font_size": "font_size", "line_spacing": "line_spacing", "margin_left": "margins",
              "margin_right": "margins", "margin_top": "margins", "margin_bottom": "margins", "pages_min": "pages",
              "pages_max": "pages", "chapters": "chapters", "sections_per_chapter": "sections", "min_sources": "references"}
METHOD_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "array", "items": {
            "type": "object",
            "properties": {"key": {"type": "string", "enum": list(METHOD_KEYS)}, "value": {"type": "string"},
                           "quote": {"type": "string"}},
            "required": ["key", "value", "quote"], "additionalProperties": False}},
        "numbers": {"type": "object", "properties": {k: {"type": "number"} for k in NUMBER_KEY},
                    "required": list(NUMBER_KEY), "additionalProperties": False},
        "font_name": {"type": "string"},
    },
    "required": ["found", "numbers", "font_name"], "additionalProperties": False,
}


def _norm(text):
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


async def analyze_method(text):
    """Faqat qo'llanmada yozilgan talablar — har biri aynan iqtibos bilan; iqtibos matnda topilmasa tashlanadi."""
    prompt = (
        "Below is an institution's methodology for dissertations. Extract ONLY requirements explicitly written in it. "
        "For each: `key`, short `value` in Uzbek, `quote` — an exact 5-25 word fragment copied from the text. "
        "`numbers`: stated values (cm, pt), 0 if not stated. `font_name`: stated font or empty.\n\nMETHODOLOGY:\n" + text
    )
    data = await ask_json(SYSTEM, prompt, METHOD_SCHEMA, max_tokens=6000, model=AI_MODEL)
    if not data:
        raise GenerationError("Metodik qo'llanmani tahlil qilib bo'lmadi. Qayta urinib ko'ring.")
    haystack = _norm(text)
    found = []
    for item in data.get("found") or []:
        words = _norm(clean(item.get("quote"))).split()
        if len(words) >= 3 and any(" ".join(words[i:i + 5]) in haystack for i in range(max(1, len(words) - 4))) \
                and clean(item.get("value")):
            found.append({"key": item["key"], "label": METHOD_KEYS[item["key"]], "value": clean(item["value"])[:300],
                          "quote": clean(item["quote"])[:300]})
    keys = {f["key"] for f in found}
    rules = {name: value for name, value in (data.get("numbers") or {}).items() if value and NUMBER_KEY[name] in keys}
    if clean(data.get("font_name")) and "font" in keys:
        rules["font_name"] = clean(data["font_name"])[:60]
    return {"found": found, "rules": rules}


# ===== Reja =====
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "enum": list(FIELDS)},
        "chapters": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "sections": {"type": "array", "items": {"type": "string"}}},
            "required": ["title", "sections"], "additionalProperties": False}},
        "search_queries": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["field", "chapters", "search_queries"], "additionalProperties": False,
}


def plan_shape(project):
    rules = project["method"].get("rules") or {}
    kind = DISS_TYPES.get(project.get("kind") or "other", DISS_TYPES["other"])
    pages = int(project["info"].get("pages") or kind["pages"])
    chapters = int(rules.get("chapters") or kind["chapters"])
    sections = int(rules.get("sections_per_chapter") or (3 if pages < 180 else 4))
    return max(2, min(6, chapters)), max(2, min(6, sections))


async def make_plan(project, materials=""):
    chapters, sections = plan_shape(project)
    prompt = head(project) + method_text(project) + (
        f"\nResearcher's materials (excerpt):\n{materials[:5000]}\n" if materials else "") + (
        f"\nCreate an individual dissertation plan: exactly {chapters} chapters, each with exactly {sections} sections. "
        "It must be specific to THIS topic and type — not a generic template. Typical logic (adapt): theoretical and "
        "methodological foundations → analysis of the current state / research → the author's model, methodology or "
        "solutions and their substantiation. Section titles must not overlap.\n"
        "`field` — the research field. `search_queries` — 8-10 short ENGLISH queries (3-6 words) to find real "
        "scientific papers in OpenAlex covering every chapter (add 'Uzbekistan' for local topics)."
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, PLAN_SCHEMA, max_tokens=5000, model=AI_MODEL)
        result = [{"title": clean(c.get("title")), "sections": [{"title": t} for t in texts(c.get("sections"))[:sections]]}
                  for c in (data or {}).get("chapters") or [] if clean(c.get("title"))][:chapters]
        if len(result) == chapters and all(len(c["sections"]) == sections for c in result):
            return {"field": data.get("field") or "other", "chapters": result, "queries": texts(data.get("search_queries"))[:10]}
        logging.warning("AI dissertatsiya rejasini noto'g'ri qaytardi")
    raise GenerationError("Rejani tuzib bo'lmadi. Iltimos, qayta urinib ko'ring.")


# ===== Hajm va vizual materiallar soni =====
def budget(project):
    pages = int(project["info"].get("pages") or 80)
    service = 7 + round(pages * 0.06)  # titul, annotatsiya, mundarija, adabiyotlar, ilovalar
    total = max(30, pages - service) * WORDS_PER_PAGE
    chapters = project["plan"]["chapters"]
    per_chapter = total * 0.86 / max(1, len(chapters))
    return {
        "intro": max(10, round(total * 0.07 / PARAGRAPH_WORDS)),
        "conclusion": max(4, round(total * 0.05 / PARAGRAPH_WORDS)),
        "sections": [[min(MAX_SECTION_PARAGRAPHS, max(3, round(per_chapter * 0.92 / len(c["sections"]) / PARAGRAPH_WORDS)))
                      for _ in c["sections"]] for c in chapters],
    }


def visuals_target(project):
    """Bitta bobga vizual materiallar soni — hajm, boblar soni va turiga qarab; tahliliy sohalarda ko'proq.
    80 betlik, 3 bobli ishda: bobga ~5 ta vizual, kamida 3 tasi rasm (jami ~15 vizual, ~9+ rasm)."""
    pages = int(project["info"].get("pages") or 80)
    chapters = max(1, len(project["plan"]["chapters"]))
    target = pages / (chapters * 6)
    if project["plan"].get("field") in ("economics", "it", "engineering", "natural"):
        target += 0.7
    if project.get("kind") == "dsc":
        target += 0.5
    return max(3, min(9, round(target)))


# ===== Kirish =====
INTRO_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"index": {"type": "integer"}, "paragraphs": {"type": "array", "items": {"type": "string"}}},
        "required": ["index", "paragraphs"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}


async def write_intro(project):
    labels = INTRO_LABELS[lang_of(project)]
    total = budget(project)["intro"]
    prompt = head(project) + method_text(project) + sources_text(project) + (
        f"\nDissertation plan:\n{plan_text(project)}\n\n"
        f"Write the INTRODUCTION (about {total} paragraphs of 90-160 words in total) as `items`, one per index:\n"
        + "\n".join(f"{i}. {label}" for i, label in enumerate(labels, 1)) +
        "\nRelevance — 2-3 paragraphs; degree of study — a review of the cited literature from the list (2-3 "
        "paragraphs); objectives map onto the plan sections; scientific novelty — 3-5 concrete proposed contributions "
        "of this work (formulated as proposed/substantiated, never as already confirmed); reliability — based on the "
        "methods, sources and (only if provided) the researcher's data; structure — the real chapters. All parts must "
        "be consistent. Do not repeat the label inside the text."
    )
    data = await ask_json(SYSTEM, prompt, INTRO_SCHEMA, max_tokens=10000, model=AI_MODEL)
    by_index = {item.get("index"): texts(item.get("paragraphs")) for item in (data or {}).get("items") or []}
    items = [{"label": label, "paragraphs": strip_citations(by_index.get(i) or [], project)} for i, label in enumerate(labels, 1)]
    if sum(1 for item in items if item["paragraphs"]) < 10:
        raise GenerationError("Kirish qismini tayyorlab bo'lmadi. Iltimos, qayta urinib ko'ring.")
    return [item for item in items if item["paragraphs"]]


# ===== Boblar =====
PARAGRAPHS_SCHEMA = {
    "type": "object",
    "properties": {"paragraphs": {"type": "array", "items": {"type": "string"}}},
    "required": ["paragraphs"], "additionalProperties": False,
}


def chapter_context(project, index):
    lines = [f"Summary of chapter {i} «{c['title']}»: " + " ".join(c["summary"])[:1000]
             for i, c in enumerate(project["chapters"][:index], 1) if c.get("summary")]
    return ("\n".join(lines) + "\n") if lines else ""


async def write_part(project, ci, si, first, count, total, materials):
    chapter = project["plan"]["chapters"][ci]
    section = chapter["sections"][si]
    last = ci == len(project["plan"]["chapters"]) - 1
    field = project["plan"].get("field") or "other"
    position = ("the whole section" if count == total else
                f"paragraphs {first}-{first + count - 1} of {total} of this section (others are written separately: "
                "opening paragraphs introduce, middle ones develop with arguments, analysis and examples, final ones conclude)")
    prompt = head(project) + method_text(project) + sources_text(project) + chapter_context(project, ci) + (
        f"\nField guidance: {FIELDS[field]}\n" if last or ci > 0 else "") + (
        f"\nResearcher's materials and data (the only allowed basis for concrete numbers; name the material):\n"
        f"{materials[:7000]}\n" if materials and ci > 0 else "") + (
        f"\nDissertation plan:\n{plan_text(project)}\n\n"
        f"Write section {ci + 1}.{si + 1} «{section['title']}» of chapter {ci + 1} «{chapter['title']}».\n"
        f"Write {position}. `paragraphs`: exactly {count} paragraphs of 120-180 words. Deep, specific, with scientific "
        "argumentation and correct terminology; distinguish theory from the author's analysis."
    )
    for _ in range(2):
        data = await ask_json(SYSTEM, prompt, PARAGRAPHS_SCHEMA, max_tokens=8000, model=AI_MODEL_WRITER)
        written = texts((data or {}).get("paragraphs"))
        if written:
            return strip_citations(written[:count], project)
        logging.warning("AI dissertatsiya bo'limini yozmadi: %s.%s", ci + 1, si + 1)
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
                "kind": {"type": "string", "enum": ["scheme", "illustration", "table", "chart", "stats"]},
                "caption": {"type": "string"}, "section": {"type": "integer"}, "paragraph": {"type": "integer"},
                "steps": {"type": "array", "items": {"type": "string"}}, "image_prompt": {"type": "string"},
                "image_query": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                "dataset": {"type": "integer"}, "chart": {"type": "string", "enum": ["bar", "line", "pie", ""]},
                "label_column": {"type": "string"}, "value_column": {"type": "string"},
            },
            "required": ["kind", "caption", "section", "paragraph", "steps", "image_prompt", "image_query", "columns",
                         "rows", "dataset", "chart", "label_column", "value_column"],
            "additionalProperties": False}},
        "topic_query": {"type": "string"},
    },
    "required": ["summary", "visuals", "topic_query"], "additionalProperties": False,
}


async def chapter_extras(project, ci, sections, datasets_text=""):
    """Bob xulosasi va vizual materiallar rejasi. Grafik/statistik jadval — faqat yuklangan ma'lumotlardan
    (dataset raqami va ustun nomlari; raqamlarni Python hisoblaydi)."""
    chapter = project["plan"]["chapters"][ci]
    target = visuals_target(project)
    outline = []
    for si, (section, paragraphs) in enumerate(zip(chapter["sections"], sections), 1):
        outline.append(f"Section {ci + 1}.{si} «{section['title']}» ({len(paragraphs)} paragraphs):")
        outline += [f"  p{pi}: {p[:200]}" for pi, p in enumerate(paragraphs, 1)]
    prompt = head(project) + (
        f"\nChapter {ci + 1} «{chapter['title']}» (beginning of every paragraph):\n" + "\n".join(outline)[:16000] +
        (f"\n\nResearcher's datasets (index: description):\n{datasets_text}\n" if datasets_text else "\n\nNo datasets uploaded.\n") +
        "\n`summary`: conclusions to this chapter — 2-3 paragraphs (100-160 words) summarising ONLY what the chapter says."
        f"\n`visuals`: {target} visual materials that explain the content, spread evenly over all sections "
        "(different sections and paragraphs, never two in a row), each after "
        "`section`/`paragraph` (1-based) where it is discussed. Kinds:\n"
        "- scheme: process / structure / research model as 3-6 boxes in `steps` (≤6 words each);\n"
        "- illustration: a realistic picture of the CONCRETE things the paragraph discusses (equipment, technology, "
        "place, process in action, people at work); `image_prompt` — one detailed English sentence naming the "
        "concrete objects, the setting (country / region if relevant to the topic) and what is happening; never "
        "abstract concepts, charts or text; `image_query` — 2-4 ENGLISH words to find a real stock photo of the "
        "same subject (main subject first, concrete and photographable). "
        f"At least {max(2, (target + 1) // 2)} of the visuals in this chapter MUST be illustrations, each showing a "
        "different subject;\n"
        "- table: comparison or classification, 2-5 `columns`, 2-8 `rows` of QUALITATIVE text only (no invented numbers);\n"
        "- chart: ONLY if a dataset exists — `dataset` (index), `chart` bar|line|pie, `label_column` and optional "
        "`value_column` (exact column names; empty value_column = count answers of a survey column);\n"
        "- stats: ONLY if a dataset exists — descriptive statistics of numeric columns: `dataset` and `columns` = exact "
        "numeric column names.\n`caption` — short title in the dissertation language. Unused fields: empty / 0.\n"
        "`topic_query` — 2-4 ENGLISH words for a stock photo of this chapter's overall subject (used if a specific "
        "photo is not found)."
    )
    data = await ask_json(SYSTEM, prompt, VISUALS_SCHEMA, max_tokens=8000, model=AI_MODEL)
    topic_query = clean((data or {}).get("topic_query"))
    summary = texts((data or {}).get("summary"))[:3]
    visuals = []
    for raw in (data or {}).get("visuals") or []:
        si, pi = int(raw.get("section") or 1) - 1, int(raw.get("paragraph") or 1) - 1
        if not (0 <= si < len(sections)) or not sections[si] or not clean(raw.get("caption")):
            continue
        item = {"kind": raw["kind"], "caption": clean(raw["caption"])[:200], "section": si,
                "paragraph": max(0, min(pi, len(sections[si]) - 1))}
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
        elif raw["kind"] == "table":
            columns = texts(raw.get("columns"))[:5]
            rows = [[clean(c)[:200] for c in row][:len(columns)] for row in raw.get("rows") or []][:8]
            rows = [row + [""] * (len(columns) - len(row)) for row in rows if any(row)]
            if len(columns) < 2 or len(rows) < 2 or any(re.search(r"\d+[.,]?\d*\s*%", c) for row in rows for c in row):
                continue
            item.update(columns=columns, rows=rows)
        elif raw["kind"] == "chart":
            item.update(dataset=int(raw.get("dataset") or 0), chart=raw.get("chart") or "bar",
                        label_column=clean(raw.get("label_column")), value_column=clean(raw.get("value_column")))
        else:  # stats
            item.update(dataset=int(raw.get("dataset") or 0), columns=texts(raw.get("columns"))[:6])
        visuals.append(item)
    return summary, visuals[:target + 1]


async def write_chapter(project, ci, materials="", datasets_text=""):
    counts = budget(project)["sections"][ci]
    sections = await run_all(*(write_section(project, ci, si, n, materials) for si, n in enumerate(counts)))
    summary, visuals = await chapter_extras(project, ci, sections, datasets_text)
    return sections, summary, visuals


# ===== Xulosa va annotatsiya =====
def intro_part(project, index):
    labels = [INTRO_LABELS[k][index] for k in INTRO_LABELS]
    return " ".join(next((i["paragraphs"] for i in project["intro"]["items"] if i["label"] in labels), []))


async def write_conclusion(project):
    total = budget(project)["conclusion"]
    summaries = "\n".join(f"Chapter {i}: " + " ".join(c.get("summary") or []) for i, c in enumerate(project["chapters"], 1))
    prompt = head(project) + (
        f"\nAim: {intro_part(project, 2)[:1200]}\nObjectives: {intro_part(project, 3)[:2500]}\n"
        f"Proposed novelty: {intro_part(project, 7)[:2000]}\n\nChapter conclusions:\n{summaries[:9000]}\n\n"
        f"Write the GENERAL CONCLUSION: exactly {total} paragraphs of 110-170 words — research results, main scientific "
        "conclusions, identified problems, proposals and recommendations, practical significance, directions for "
        "future research, and how the aim and objectives were achieved. Use ONLY what appears in the chapter "
        "conclusions; results not confirmed in practice are presented as substantiated proposals, not as proven facts."
    )
    data = await ask_json(SYSTEM, prompt, PARAGRAPHS_SCHEMA, max_tokens=8000, model=AI_MODEL)
    paragraphs = texts((data or {}).get("paragraphs"))
    if not paragraphs:
        raise GenerationError("Xulosani yozib bo'lmadi. Iltimos, qayta urinib ko'ring.")
    return strip_citations(paragraphs[:total + 1], project)


ANNOTATION_SCHEMA = {
    "type": "object",
    "properties": {"paragraphs": {"type": "array", "items": {"type": "string"}},
                   "keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["paragraphs", "keywords"], "additionalProperties": False,
}


async def write_annotation(project):
    prompt = head(project) + (
        f"\nAim: {intro_part(project, 2)[:1000]}\nMethods: {intro_part(project, 6)[:1200]}\n"
        f"Novelty: {intro_part(project, 7)[:1500]}\nConclusion: {' '.join(project['conclusion']['paragraphs'])[:4000]}\n\n"
        "Write the ANNOTATION (abstract) of the dissertation: 2-3 paragraphs, 220-320 words in total — relevance, aim, "
        "methods, main results (as in the conclusion) and significance; no citations, no new claims. "
        "`keywords`: 6-8 key terms of the dissertation."
    )
    data = await ask_json(SYSTEM, prompt, ANNOTATION_SCHEMA, max_tokens=3000, model=AI_MODEL)
    paragraphs, keywords = texts((data or {}).get("paragraphs")), [k[:60] for k in texts((data or {}).get("keywords"))][:8]
    if not paragraphs:
        raise GenerationError("Annotatsiyani yozib bo'lmadi. Iltimos, qayta urinib ko'ring.")
    return strip_citations(paragraphs[:3], project), keywords


# ===== Mazmuniy muvofiqlik tekshiruvi (sifat nazorati) =====
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {
        "type": "object",
        "properties": {"severity": {"type": "string", "enum": ["warning", "info"]}, "part": {"type": "string"},
                       "problem": {"type": "string"}, "suggestion": {"type": "string"}},
        "required": ["severity", "part", "problem", "suggestion"], "additionalProperties": False}}},
    "required": ["issues"], "additionalProperties": False,
}


async def review(project):
    """Kirish (maqsad, vazifalar, yangilik), reja, bob xulosalari va umumiy xulosa bir-biriga mosmi — AI ko'rib chiqadi."""
    summaries = "\n".join(f"Chapter {i} «{c['title']}»: " + " ".join(c.get("summary") or [])
                          for i, c in enumerate(project["chapters"], 1))
    prompt = head(project) + (
        f"\nPlan:\n{plan_text(project)}\n\nAim: {intro_part(project, 2)[:1200]}\nObjectives: {intro_part(project, 3)[:2500]}\n"
        f"Proposed novelty: {intro_part(project, 7)[:2000]}\n\nChapter conclusions:\n{summaries[:9000]}\n\n"
        f"General conclusion: {' '.join(project['conclusion']['paragraphs'])[:5000]}\n\n"
        "Act as a strict scientific reviewer. Check ONLY consistency: does every objective get covered by a chapter; "
        "do the conclusions match the objectives and novelty; are there claims of confirmed results, implementation "
        "or approbation without data; are chapters logically connected; does the topic stay consistent. List up to 10 "
        "concrete `issues` in Uzbek (`part` — which part, `problem`, `suggestion`). Empty list if all is consistent."
    )
    data = await ask_json(SYSTEM, prompt, REVIEW_SCHEMA, max_tokens=4000, model=AI_MODEL)
    return [{k: clean(i.get(k))[:500] for k in ("severity", "part", "problem", "suggestion")}
            for i in (data or {}).get("issues") or [] if clean(i.get("problem"))][:10]


# ===== Tahrirlash amallari =====
OPS = {
    "expand": "Expand the paragraph to about 1.5x length with more scientific argumentation and an example; keep the meaning.",
    "shorten": "Shorten the paragraph to about 60% of its length, keeping the key ideas and citations.",
    "fix": "Fix spelling, grammar and punctuation only; do not change the content or style.",
    "style": "Bring the paragraph to a rigorous scientific academic style; keep the content and all [n] citations.",
    "regenerate": "Rewrite the paragraph from scratch with the same role, without repeating its wording.",
}
ONE_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}


async def rewrite(project, text, op, where):
    prompt = head(project) + sources_text(project) + (
        f"\nThe paragraph belongs to: {where}\n\nPARAGRAPH:\n{text}\n\nTask: {OPS[op]} Return the new paragraph in `text`.")
    data = await ask_json(SYSTEM, prompt, ONE_SCHEMA, max_tokens=3500, model=AI_MODEL_WRITER if op == "fix" else AI_MODEL)
    result = clean((data or {}).get("text"))
    if not result:
        raise GenerationError("Matnni o'zgartirib bo'lmadi. Qayta urinib ko'ring.")
    return strip_citations([result], project)[0]
