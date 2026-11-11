import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


# ===== .env faylini o'qish =====
def load_env():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env()
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Bot egasi (bosh admin) — sizning Telegram ID'ingiz. Faqat u boshqa adminlarni qo'sha / o'chira oladi (admins.py)
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID", "").isdecimal() else None
# Egadan tashqari nechta qo'shimcha admin bo'lishi mumkin (botda /adminlar yoki web admin panel orqali qo'shiladi)
ADMINS_EXTRA_MAX = int(os.getenv("ADMINS_EXTRA_MAX", "2"))

# Ma'lumotlar (baza) papkasi — serverda/Docker'da alohida diskka ulanadi, qayta o'rnatishda yo'qolmaydi
# Nisbiy yo'l (masalan ../data) bot papkasiga nisbatan olinadi — web server (server/src/config.js) ham shunday qiladi
DATA_DIR = (BASE_DIR / os.getenv("DATA_DIR", ".")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bot.db"

# ===== Taqdimot (AI) =====
# Claude API kaliti .env faylidagi ANTHROPIC_API_KEY dan o'qiladi
# Xarajatni tejash uchun ish ikki modelga bo'lingan (.env da o'zgartirsa bo'ladi):
#   AI_MODEL — reja va sarlavhalar (kichik, lekin tuzilma sifati muhim)
#   AI_MODEL_WRITER — asosiy matn (barcha tokenlarning ~90% i) — Opus'dan ~40 baravar arzon va tezroq
# Sifat yetmasa: AI_MODEL_WRITER=claude-sonnet-5-5 (yoki eng sifatli, lekin qimmat claude-opus-5-5)
AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-5-5")
AI_MODEL_WRITER = os.getenv("AI_MODEL_WRITER", "claude-haiku-5-5")
# Claude'ga bir vaqtda ketadigan so'rovlar (hisobning «concurrent requests» limitidan oshmasin; tarif oshsa ko'paytiring)
API_CONCURRENCY = int(os.getenv("API_CONCURRENCY", "20"))
PLAN_MIN, PLAN_MAX = 1, 10  # reja bandlari soni (1 — kichik taqdimotlar uchun: 5 slayd = 1 reja)
SLIDE_OPTIONS = (5, 8) + tuple(range(10, 61, 5)) + (70, 80)  # tanlash uchun: 5, 8, 10, 15, ..., 60, 70, 80
SLIDES_MAX = SLIDE_OPTIONS[-1]
FIXED_SLIDES = 4  # muqova, mundarija, reja, xulosa — shuning uchun slaydlar kamida «reja soni + 4»
AI_CONCURRENCY = 5  # bir vaqtda nechta buyurtma tayyorlanadi (qolganlari navbatda kutadi)

# Rasmlar manbasi (birinchi topilgan kalit ishlatiladi): Pexels → Pixabay → Wikimedia Commons (kalitsiz)
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
# Shablonlar (Korporativ, Daftar, Tarix, Barokko) rasmlari AI bilan generatsiya qilinadi — Google Gemini.
# Kalit: aistudio.google.com → Get API key. Yozilmasa yoki generatsiya ishlamasa — rasmlar yuqoridagi manbadan olinadi
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Arzonroq va tezroq: gemini-3.1-flash-lite-image; eng sifatli: gemini-3-pro-image
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1").strip()
GEMINI_CONCURRENCY = int(os.getenv("GEMINI_CONCURRENCY", "6"))  # bir vaqtda nechta rasm chiziladi
# BEPUL variant — Cloudflare Workers AI (FLUX-1 schnell): kuniga ~10 000 «neyron» bepul (~130 rasm), karta shart emas.
# dash.cloudflare.com → Account ID va «Workers AI» ruxsatli API token. Gemini kaliti ham bo'lsa — Gemini ishlatiladi
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()


IMAGES_MAX = 30  # bitta taqdimotga eng ko'p rasm
IMAGE_SHARE = 0.7  # ichki slaydlarning qancha qismida rasm bo'ladi


def image_count(slides):
    """Taqdimotdagi rasmlar soni: ichki mavzu slaydlarining ~70 % i (10 slayddan 7 tasida rasm),
    kamida 1 ta, ko'pi bilan IMAGES_MAX. Muqova, mundarija, reja va xulosa — rasmsiz.
    Har bir rasm AI tekshiruvidan o'tadi, mos foto bo'lmasa — slayd mazmuni bo'yicha AI chizadi:
    5 → 1, 8 → 3, 10 → 4, 15 → 8, 20 → 11, 30 → 18, 40 → 25, 50 → 30."""
    inner = max(1, slides - FIXED_SLIDES)
    return max(1, min(IMAGES_MAX, int(inner * IMAGE_SHARE + 0.5)))


def image_plan_text():
    """Botdagi yordam matni uchun — image_count bilan doim bir xil (alohida yozilmaydi)."""
    return ", ".join(f"{n} slaydga — {image_count(n)} ta" for n in (5, 8, 10, 15, 20, 30, 40, 50))


# ===== AI yordamchi (bepul tez yaratish: reja va matn — sayt va bot uchun umumiy) =====
AI_ASSISTANT_MODEL = os.getenv("AI_ASSISTANT_MODEL", "claude-sonnet-5-5")
AI_ASSISTANT_DAILY_LIMIT = int(os.getenv("AI_ASSISTANT_DAILY_LIMIT", "3"))  # bitta userga kuniga bepul
AI_ASSISTANT_PER_MINUTE = int(os.getenv("AI_ASSISTANT_PER_MINUTE", "2"))  # daqiqasiga so'rovlar
AI_ASSISTANT_TIMEOUT = 90  # bitta AI so'rovi uchun, soniya

# Claude'ga bir kunda sarflanadigan eng ko'p summa (USD). Yetganda AI to'xtaydi, adminga xabar boradi.
# 80% ida ogohlantirish keladi. 0 — chegara yo'q. Sarfni ko'rish: botda /xarajat (ai_usage.py)
try:
    AI_DAILY_BUDGET_USD = max(0.0, float(os.getenv("AI_DAILY_BUDGET_USD", "3")))
except ValueError:
    AI_DAILY_BUDGET_USD = 3.0


# ===== To'lov =====
def parse_cards(raw):
    """.env dagi PAYMENT_CARDS ni o'qiydi: «8600 1234 5678 9012 | Aliyev Vali; 9860 ... | ...»"""
    cards = []
    for part in raw.split(";"):
        number, _, holder = part.partition("|")
        if number.strip():
            cards.append((" ".join(number.split()), holder.strip()))
    return cards


PAYMENT_CARDS = parse_cards(os.getenv("PAYMENT_CARDS", ""))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")  # savollar uchun admin username (ixtiyoriy)
# Web ilova (slayd-web) manzili — https bo'lishi shart. Yozilsa, botning menyu tugmasi ilovani ochadi
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
TOPUP_MIN, TOPUP_MAX = 5_000, 5_000_000  # bir martalik to'ldirish chegarasi (so'm)
TOPUP_OPTIONS = (10_000, 20_000, 50_000, 100_000)
PENDING_MAX = 3  # bir userda bir vaqtda tekshiruvni kutayotgan cheklar soni

# ===== Narxlar (so'm) =====
SLIDE_PRICE = 500  # taqdimotning har bir slaydi
# Matnli ishlar: tanlash uchun betlar soni va har bir bet narxi
PAGE_OPTIONS = {
    "referat": (5, 10, 15, 20, 25, 30),
    "mustaqil": (5, 10, 15, 20, 25, 30),
    "kurs": (20, 25, 30, 35, 40, 45, 50),
}
# Foydalanuvchi o'zi yozishi mumkin bo'lgan betlar oralig'i (tugmalardagi variantlardan kengroq) — bot va sayt uchun umumiy
PAGE_RANGE = {"referat": (3, 50), "mustaqil": (3, 50), "kurs": (15, 80)}
PAGE_PRICE = {"referat": 500, "mustaqil": 500, "kurs": 600}

# Diplom ishi (diploma/): betlar sonini foydalanuvchi o'zi tanlaydi (tayyor variantlar yoki istalgan son)
DIPLOM_PAGE_PRICE = 700
DIPLOM_PAGES_MIN, DIPLOM_PAGES_MAX = 40, 150
DIPLOM_PAGE_OPTIONS = (50, 60, 70, 80, 90, 100)
# Pul yechilgandan keyin bepul AI amallari (bobni qayta yozish, xatboshini kengaytirish ...) — kuniga bitta ishga
DIPLOM_AI_OPS_DAILY = 60
DIPLOM_PLANS_DAILY = 10  # to'lovgacha bepul reja tuzish (suiiste'mol bo'lmasin)

# Dissertatsiya (dissertation/): turi → standart hajm (betlar) va boblar soni. Betlarni foydalanuvchi o'zi tanlaydi
DISS_PAGE_PRICE = 800
DISS_PAGES_MIN, DISS_PAGES_MAX = 50, 300
DISS_TYPES = {
    "master": {"name": "Magistrlik dissertatsiyasi", "pages": 80, "options": (70, 80, 90, 100), "chapters": 3},
    "phd": {"name": "PhD dissertatsiyasi", "pages": 140, "options": (120, 130, 140, 150, 160), "chapters": 3},
    "dsc": {"name": "DSc dissertatsiyasi", "pages": 220, "options": (200, 220, 250), "chapters": 4},
    "other": {"name": "Boshqa ilmiy tadqiqot", "pages": 80, "options": (60, 80, 100, 120), "chapters": 3},
}
DISS_AI_OPS_DAILY = 80  # to'lovdan keyin bepul AI amallari (kuniga bitta ishga)
DISS_PLANS_DAILY = 12  # to'lovgacha bepul: reja va mavzu takliflari


def money(amount):
    return f"{amount:,}".replace(",", " ") + " so'm"


def presentation_price(slides):
    return slides * SLIDE_PRICE


def document_price(kind, pages):
    return pages * PAGE_PRICE[kind]


# ===== Maqola (articles/): narx so'zlar soniga qarab — har 100 so'z uchun, kamida ARTICLE_PRICE_MIN =====
ARTICLE_PRICE_PER_100 = int(os.getenv("ARTICLE_PRICE_PER_100", "200"))
ARTICLE_PRICE_MIN = int(os.getenv("ARTICLE_PRICE_MIN", "1500"))
ARTICLE_WORDS_MIN, ARTICLE_WORDS_MAX = 300, 5000


def article_price(words):
    return max(ARTICLE_PRICE_MIN, -(-int(words) // 100) * ARTICLE_PRICE_PER_100)


def price_lines():
    def pages(kind):
        low, high = PAGE_RANGE[kind]
        return f"{low}–{high} bet (o'zingiz tanlaysiz), har bir bet <b>{money(PAGE_PRICE[kind])}</b>"

    return "\n".join([
        f"   📊 <b>Taqdimot:</b> {SLIDE_OPTIONS[0]}–{SLIDES_MAX} slayd, har bir slayd <b>{money(SLIDE_PRICE)}</b>",
        f"   📄 <b>Referat:</b> {pages('referat')}",
        f"   ✍️ <b>Mustaqil ish:</b> {pages('mustaqil')}",
        f"   📚 <b>Kurs ishi:</b> {pages('kurs')}",
        f"   🎓 <b>Diplom ishi:</b> {DIPLOM_PAGES_MIN}–{DIPLOM_PAGES_MAX} bet, har bir bet <b>{money(DIPLOM_PAGE_PRICE)}</b>",
        f"   🔬 <b>Dissertatsiya:</b> {DISS_PAGES_MIN}–{DISS_PAGES_MAX} bet, har bir bet <b>{money(DISS_PAGE_PRICE)}</b>",
    ])
