"""Avtomatik sifat nazorati (yakuniy fayldan oldin). Har bir tekshiruv: {"key", "label", "status", "detail"}.
status: ok — joyida, warn — e'tibor bering, error — tuzatish kerak, skip — avtomatik tekshirib bo'lmaydi (ochiq aytiladi).
Mazmuniy muvofiqlik (kirish ↔ boblar ↔ xulosa) — alohida, AI ko'rib chiqadi (ai.review)."""
import re
from collections import Counter

from dissertation.ai import WORDS_PER_PAGE
from dissertation.docx_builder import CITE, all_texts
from dissertation.storage import SAFE_NAME

STOP = {"tadqiqot", "asoslari", "masalalari", "takomillashtirish", "rivojlantirish", "yo'llari", "o'rni", "ahamiyati",
        "xususiyatlari", "holati", "tahlili", "boshqarish", "sharoitida", "asosida", "orqali", "uchun", "bilan"}


def check(key, label, status, detail):
    return {"key": key, "label": label, "status": status, "detail": detail}


def words(text):
    return re.findall(r"[\wʻʼ'’-]+", text.lower())


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 9]


def run_checks(project, folder):
    out = []
    plan, chapters = project["plan"]["chapters"], project["chapters"]

    # 1. Barcha qismlar yozilgan va tasdiqlanganmi
    parts = [("Kirish", project["intro"], bool(project["intro"]["items"]))]
    parts += [(f"{i + 1}-bob", c, any(s["paragraphs"] for s in c["sections"])) for i, c in enumerate(chapters)]
    parts += [("Xulosa", project["conclusion"], bool(project["conclusion"]["paragraphs"])),
              ("Annotatsiya", project["annotation"], bool(project["annotation"]["paragraphs"]))]
    missing = [name for name, _, written in parts if not written]
    unapproved = [name for name, part, written in parts if written and part.get("status") != "approved"]
    out.append(check("parts", "Barcha qismlar yozilganmi", "error" if missing else "warn" if unapproved else "ok",
                     f"Yozilmagan: {', '.join(missing)}" if missing else
                     f"Tasdiqlanmagan: {', '.join(unapproved)}" if unapproved else "Hammasi yozilgan va tasdiqlangan"))

    # 2. Reja va matn mosligi
    problems = []
    for i, (p, c) in enumerate(zip(plan, chapters), 1):
        if p["title"] != c["title"] or len(p["sections"]) != len(c["sections"]):
            problems.append(f"{i}-bob tuzilmasi rejadan farq qiladi")
        problems += [f"{i}.{j}-paragrafda matn juda kam" for j, s in enumerate(c["sections"], 1)
                     if any(s["paragraphs"]) and len(s["paragraphs"]) < 2]
    out.append(check("plan", "Reja va asosiy matn mosligi", "warn" if problems else "ok",
                     "; ".join(problems[:5]) or "Boblar va paragraflar rejaga mos"))

    # 3. Takroriy gaplar
    counter = Counter(re.sub(r"\W+", " ", s.lower()) for t in all_texts(project) for s in sentences(t))
    repeated = [s for s, n in counter.items() if n > 1]
    out.append(check("repeats", "Matnda takrorlar", "warn" if repeated else "ok",
                     f"{len(repeated)} ta gap bir necha marta uchraydi, masalan: «{repeated[0][:120]}…»" if repeated
                     else "Takroriy gaplar topilmadi"))

    # 4. Iqtiboslar ↔ adabiyotlar
    known = {s["n"] for s in project["sources"]}
    cited = {int(n) for t in all_texts(project) for g in CITE.findall(t) for n in g.split(",")}
    dangling, uncited = cited - known, known - cited
    status = "error" if dangling else "warn" if uncited and len(uncited) > len(known) / 2 else "ok"
    out.append(check("citations", "Iqtiboslar va adabiyotlar mosligi", status,
                     f"Ro'yxatda yo'q manbaga havola: {sorted(dangling)}" if dangling else
                     f"{len(cited & known)} ta manbaga matnda havola bor; {len(uncited)} tasi faqat ro'yxatda "
                     "(faylda ro'yxat oxirida turadi)"))

    # 5. Manbalar haqiqiyligi
    verified = sum(1 for s in project["sources"] if s.get("verified"))
    total = len(project["sources"])
    minimum = int((project["method"].get("rules") or {}).get("min_sources") or 0)
    status = "error" if not total else "warn" if verified < total or (minimum and total < minimum) else "ok"
    out.append(check("sources", "Manbalar haqiqiyligi", status,
                     f"{verified}/{total} tasi OpenAlex/Crossref bazasida tekshirilgan (DOI yoki havola bilan)"
                     + (f"; {total - verified} tasi qo'lda qo'shilgan — tekshirilmagan" if verified < total else "")
                     + (f"; qo'llanma kamida {minimum} ta manba talab qiladi" if minimum and total < minimum else "")))

    # 6. Rasm, grafik va jadvallar
    figures = [f for c in chapters for f in c.get("figures") or []]
    broken = [f["caption"] for f in figures if f["kind"] != "table" and
              not (f.get("file") and SAFE_NAME.match(f["file"]) and (folder / f["file"]).is_file())]
    data_based = sum(1 for f in figures if f.get("dataset"))
    ai_made = sum(1 for f in figures if f["kind"] == "illustration")
    out.append(check("figures", "Rasmlar, grafiklar va jadvallar", "error" if broken else "ok" if figures else "warn",
                     f"Fayli yo'q: {', '.join(broken[:3])}" if broken else
                     f"{len(figures)} ta vizual material; {data_based} tasi sizning ma'lumotlaringizdan, "
                     f"{ai_made} tasi AI illyustratsiyasi (manbasi ko'rsatilgan); raqamlash va havolalar faylda avtomatik"
                     if figures else "Vizual materiallar yo'q"))

    # 7. Hajm
    words_total = sum(len(t.split()) for t in all_texts(project))
    estimated = round(words_total / WORDS_PER_PAGE) + 7 + round(len(figures) * 0.5)
    target = int(project["info"].get("pages") or 80)
    status = "ok" if abs(estimated - target) <= target * 0.15 else "warn"
    out.append(check("volume", "Hajmi", status, f"Taxminan {estimated} bet (rejalashtirilgan {target} bet)"))

    # 8. Mavzuning izchilligi — mavzu so'zlari har bir bobda bormi
    keys = {w[:6] for w in words(project["info"]["topic"]) if len(w) >= 5 and w not in STOP}
    weak = []
    for i, c in enumerate(chapters, 1):
        text = " ".join(p for s in c["sections"] for p in s["paragraphs"])
        if text and keys and len(keys & {w[:6] for w in words(text)}) < max(1, len(keys) // 2):
            weak.append(f"{i}-bob")
    out.append(check("topic", "Mavzu barcha boblarda yoritilganmi", "warn" if weak else "ok",
                     f"Mavzuning asosiy tushunchalari kam uchraydi: {', '.join(weak)}" if weak else
                     "Mavzuning asosiy tushunchalari har bir bobda uchraydi"))

    # 9. Avtomatik tekshirib bo'lmaydiganlar — ochiq aytiladi
    out.append(check("spelling", "Imlo va grammatika", "skip",
                     "To'liq avtomatik tekshirilmadi — har bir xatboshida «Imloni tuzatish» amali bor"))
    out.append(check("toc", "Mundarija va sahifa raqamlari", "skip",
                     "Word maydoni sifatida qo'yiladi — fayl Word'da ochilganda yangilanadi (oldindan tekshirib bo'lmaydi)"))
    return out
