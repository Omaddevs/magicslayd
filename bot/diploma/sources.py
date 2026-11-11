"""Haqiqiy ilmiy manbalar: OpenAlex (asosiy) va Crossref (zaxira) — ikkalasi ham bepul va kalitsiz.

AI manba O'YLAB TOPMAYDI: faqat shu bazalarda haqiqatan mavjud ishlar (muallif, nom, yil, nashr, DOI, havola)
olinadi va «tekshirilgan» deb belgilanadi. Foydalanuvchi qo'lda qo'shgan manba esa «tekshirilmagan» bo'ladi."""
import asyncio
import logging
import re

import aiohttp

OPENALEX = "https://api.openalex.org/works"
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "SlaydReferatBot/1.0 (https://t.me/slayd_referatai_bot)"
TIMEOUT = aiohttp.ClientTimeout(total=20, connect=8)
TYPES = {"article", "book", "book-chapter", "review", "journal-article", "monograph", "dissertation", "proceedings-article"}


def _clean(text):
    return re.sub(r"<[^>]+>", "", " ".join(str(text or "").split())).strip()


def _authors(names):
    names = [n for n in names if n][:3]
    return ", ".join(names) + (" va boshq." if len(names) == 3 else "") if names else ""


def _key(item):
    return (item.get("doi") or "").lower() or re.sub(r"\W+", "", item["title"].lower())[:80]


async def _openalex(session, query, per_page):
    params = {
        "search": query, "per-page": per_page,
        "select": "doi,display_name,publication_year,authorships,primary_location,type,cited_by_count,is_retracted",
    }
    async with session.get(OPENALEX, params=params) as response:
        if response.status != 200:
            logging.warning("OpenAlex %s: %s", response.status, query)
            return []
        data = await response.json()
    items = []
    for work in data.get("results", []):
        if work.get("is_retracted") or work.get("type") not in TYPES:
            continue
        title, year = _clean(work.get("display_name")), work.get("publication_year")
        authors = _authors([(a.get("author") or {}).get("display_name") for a in work.get("authorships") or []])
        if not title or not year or not authors:
            continue
        location = work.get("primary_location") or {}
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        items.append({
            "authors": authors, "title": title[:300], "year": int(year),
            "venue": _clean((location.get("source") or {}).get("display_name"))[:200],
            "doi": doi, "url": work.get("doi") or location.get("landing_page_url") or "",
            "verified": True, "origin": "OpenAlex", "cited": work.get("cited_by_count") or 0,
        })
    return items


async def _crossref(session, query, rows):
    params = {"query.bibliographic": query, "rows": rows, "select": "DOI,title,author,issued,container-title,type,URL"}
    async with session.get(CROSSREF, params=params) as response:
        if response.status != 200:
            logging.warning("Crossref %s: %s", response.status, query)
            return []
        data = await response.json()
    items = []
    for work in (data.get("message") or {}).get("items", []):
        title = _clean((work.get("title") or [""])[0])
        year = ((work.get("issued") or {}).get("date-parts") or [[None]])[0][0]
        names = [" ".join(filter(None, (a.get("given"), a.get("family")))) for a in work.get("author") or []]
        authors = _authors(names)
        if not title or not year or not authors or work.get("type") not in TYPES:
            continue
        items.append({
            "authors": authors, "title": title[:300], "year": int(year),
            "venue": _clean((work.get("container-title") or [""])[0])[:200],
            "doi": work.get("DOI") or "", "url": work.get("URL") or "",
            "verified": True, "origin": "Crossref", "cited": 0,
        })
    return items


async def find_sources(queries, limit=30):
    """Har bir so'rov bo'yicha qidiradi va natijalarni navbatma-navbat (har bir mavzudan) birlashtiradi.
    Hech qachon xato tashlamaydi — internet bo'lmasa bo'sh ro'yxat."""
    queries = [q for q in dict.fromkeys(_clean(q) for q in queries) if q][:10]
    if not queries:
        return []
    per_query = max(5, min(15, limit // len(queries) + 4))
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as session:
            results = await asyncio.gather(*(_openalex(session, q, per_query) for q in queries), return_exceptions=True)
            lists = [r if isinstance(r, list) else [] for r in results]
            if sum(map(len, lists)) < limit // 2:  # OpenAlex kam topsa — Crossref
                extra = await asyncio.gather(*(_crossref(session, q, per_query) for q in queries), return_exceptions=True)
                lists += [r if isinstance(r, list) else [] for r in extra]
    except Exception:
        logging.exception("Manbalarni qidirishda xato")
        return []
    picked, seen = [], set()
    for round_ in range(max(map(len, lists), default=0)):
        for items in lists:
            if round_ < len(items) and _key(items[round_]) not in seen and len(picked) < limit:
                seen.add(_key(items[round_]))
                picked.append(items[round_])
    return picked


def format_source(item, lang="uz"):
    """Adabiyotlar ro'yxatidagi ko'rinish: «Muallif. Nomi // Nashr. — Yil. — DOI/URL»."""
    parts = [f"{item['authors'].rstrip('.')}. {item['title']}"]
    if item.get("venue"):
        parts.append(f" // {item['venue']}")
    parts.append(f". — {item['year']}.")
    if item.get("doi"):
        parts.append(f" — DOI: {item['doi']}")
    elif item.get("url"):
        parts.append(f" — URL: {item['url']}")
    return "".join(parts)
