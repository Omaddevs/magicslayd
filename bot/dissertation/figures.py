"""Dissertatsiyaning vizual materiallari (ai.chapter_extras rejasi bo'yicha):
- scheme — jarayon / model sxemasi (bob matnidan, raqamsiz);
- illustration — mavzuga mos ilmiy illyustratsiya (AI chizadi; chizilmasa — shu mavzudagi haqiqiy foto);
- chart — ustunli / chiziqli / doiraviy grafik: FAQAT foydalanuvchi yuklagan jadval ma'lumotlaridan;
- stats — tavsifiy statistika jadvali: raqamlar Python'da hisoblanadi;
- table — sifat (matnli) taqqoslash jadvali.
Har birining manbasi saqlanadi va faylda ko'rsatiladi."""
import logging
import uuid

from diploma.figures import SOURCE_PHOTO, illustrate, scheme
from dissertation import charts, datasets

ILLUSTRATION_STYLE = ("photorealistic documentary photograph for a scientific monograph, DSLR, 35mm lens, natural colors, "
                      "sharp focus, soft natural lighting, clean uncluttered composition, academic publication quality")
SOURCE = {
    "uz": {"author": "Muallif tomonidan tuzilgan", "ai": "AI yordamida yaratilgan illyustratsiya",
           "data": "«{name}» ma'lumotlari asosida muallif hisob-kitobi"},
    "ru": {"author": "Составлено автором", "ai": "Иллюстрация создана с помощью ИИ",
           "data": "Расчёты автора по данным «{name}»"},
    "en": {"author": "Compiled by the author", "ai": "Illustration generated with AI",
           "data": "Author's calculations based on «{name}»"},
}
STATS_HEAD = {
    "uz": ["Ko'rsatkich", "Kuzatuvlar soni", "Eng kichik", "Eng katta", "O'rtacha", "Jami"],
    "ru": ["Показатель", "Число наблюдений", "Минимум", "Максимум", "Среднее", "Сумма"],
    "en": ["Indicator", "Observations", "Minimum", "Maximum", "Mean", "Total"],
}


async def make_figures(folder, visuals, topic, lang, tables):
    """tables — [(nomi, sarlavhalar, qatorlar), ...] (ai'ga berilgan tartibda). Yaroqsiz vizuallar tashlanadi."""
    source = SOURCE.get(lang, SOURCE["uz"])
    folder.mkdir(parents=True, exist_ok=True)
    # AI chizadi; chiza olmaganlari — mavzuga mos foto (diploma/figures.py → illustrate). Hech biri bekorga tashlanmaydi
    images = await illustrate([v for v in visuals if v["kind"] == "illustration"], topic, ILLUSTRATION_STYLE)
    result = []
    for visual in visuals:
        item = {k: visual[k] for k in ("kind", "caption", "section", "paragraph")}
        item["id"] = uuid.uuid4().hex[:10]
        kind = visual["kind"]
        try:
            if kind == "table":
                item.update(columns=visual["columns"], rows=visual["rows"], source=source["author"])
            elif kind in ("chart", "stats"):
                if not 0 <= visual["dataset"] < len(tables):
                    continue
                name, headers, rows = tables[visual["dataset"]]
                if kind == "chart":
                    labels, values = datasets.series(headers, rows, visual["label_column"], visual["value_column"] or None)
                    if len(labels) < 2:
                        continue
                    data = charts.render(visual["chart"], labels, values, visual["value_column"])
                    item.update(file=_save(folder, data, "png"), chart=visual["chart"], dataset=name,
                                label_column=visual["label_column"], value_column=visual["value_column"])
                else:
                    summary = {c["name"]: c for c in datasets.summarize(headers, rows)["columns"] if c["numeric"]}
                    picked = [summary[c] for c in visual["columns"] if c in summary]
                    if not picked:
                        continue
                    fmt = charts.fmt
                    item.update(kind="table", columns=STATS_HEAD.get(lang, STATS_HEAD["uz"]), dataset=name,
                                stat_columns=[c["name"] for c in picked],
                                rows=[[c["name"], str(c["count"]), fmt(c["min"]), fmt(c["max"]), fmt(c["mean"]), fmt(c["sum"])]
                                      for c in picked])
                item["source"] = source["data"].format(name=name)
            else:
                data, origin = (scheme(visual["steps"]), "scheme") if kind == "scheme" else images.get(id(visual), (None, None))
                if not data:
                    continue
                item["file"] = _save(folder, data, "png" if kind == "scheme" else "jpg")
                item["source"] = {"scheme": source["author"], "ai": source["ai"],
                                  "photo": SOURCE_PHOTO.get(lang, SOURCE_PHOTO["uz"])}[origin]
                if kind == "scheme":
                    item["steps"] = visual["steps"]
        except (datasets.DataError, ValueError) as e:
            logging.info("Vizual material tashlandi (%s): %s", kind, e)
            continue
        result.append(item)
    return result


def _save(folder, data, ext):
    name = f"fig-{uuid.uuid4().hex[:10]}.{ext}"
    (folder / name).write_bytes(data)
    return name
