from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from config import (
    FIXED_SLIDES, PAGE_OPTIONS, PLAN_MAX, PLAN_MIN, SLIDE_OPTIONS, TOPUP_OPTIONS, WEBAPP_URL, document_price, money,
    presentation_price,
)
from presentation.ai import LANGUAGES
from presentation.themes import THEMES

Button = InlineKeyboardButton


def inline(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows])


# ===== Bosh menyu (pastdagi doimiy tugmalar) =====
BTN_PRES, BTN_REFERAT = "📊 Prezentatsiya", "📄 Referat"
BTN_MUSTAQIL, BTN_KURS = "✍️ Mustaqil ish", "📚 Kurs ishi"
BTN_FILES, BTN_BALANCE = "📂 Hujjatlarim", "💎 Balans"
BTN_TITLE, BTN_OTHER = "👤 Titul ma'lumotlari", "🧰 Boshqa xizmatlar"
BTN_AI = "🤖 AI yordamchi"
BTN_DIPLOM = "🎓 Diplom ishi"
BTN_DISS = "🔬 Dissertatsiya"
BTN_ACCOUNT = "🔐 Hisobim"
BTN_ARTICLE = "📝 Maqola"
DOC_BUTTONS = {BTN_REFERAT: "referat", BTN_MUSTAQIL: "mustaqil", BTN_KURS: "kurs"}
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=text) for text in row]
        for row in (
            (BTN_KURS, BTN_MUSTAQIL), (BTN_REFERAT, BTN_PRES), (BTN_DIPLOM, BTN_DISS), (BTN_ARTICLE,),
            (BTN_AI, BTN_ACCOUNT), (BTN_FILES, BTN_BALANCE), (BTN_TITLE, BTN_OTHER),
        )
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def other_menu(support_username):
    rows = [
        [Button(text="🎨 Taqdimot dizaynlari", callback_data="designs")],
        [Button(text="ℹ️ Yordam va narxlar", callback_data="help")],
    ]
    if support_username:
        rows.append([Button(text="💬 Admin bilan bog'lanish", url=f"https://t.me/{support_username}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ===== Hamyon =====
wallet_menu = inline(
    [Button(text="➕ Hisobni to'ldirish", callback_data="wallet_topup")],
    [Button(text="📜 Tarix", callback_data="wallet_history")],
)
wallet_back_menu = inline([Button(text="⬅️ Orqaga", callback_data="wallet")])


def topup_amount_menu(suggest=None, back="wallet"):
    amounts = ([suggest] if suggest else []) + [n for n in TOPUP_OPTIONS if n != suggest]
    buttons = [
        Button(text=f"{'⭐ ' if n == suggest else ''}{money(n)}", callback_data=f"topup:{n}") for n in amounts
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        *[buttons[i:i + 2] for i in range(0, len(buttons), 2)],
        [Button(text="⬅️ Orqaga", callback_data=back)],
    ])


topup_check_menu = inline(
    [Button(text="✏️ Summani o'zgartirish", callback_data="wallet_topup")],
    [Button(text="❌ Bekor qilish", callback_data="wallet")],
)
topup_done_menu = inline([Button(text="↩️ Buyurtmani davom ettirish", callback_data="resume")])
topup_rejected_menu = inline([Button(text="🔄 Qayta yuborish", callback_data="wallet_topup")])


def payment_review_menu(payment_id):
    return inline(
        [
            Button(text="✅ Tasdiqlash", callback_data=f"pay_ok:{payment_id}"),
            Button(text="❌ Rad etish", callback_data=f"pay_no:{payment_id}"),
        ],
        [Button(text="💬 Userga yozish", callback_data=f"pay_msg:{payment_id}")],
    )


def payment_done_menu(payment_id):
    return inline([Button(text="💬 Userga yozish", callback_data=f"pay_msg:{payment_id}")])


admin_reply_cancel_menu = inline([Button(text="❌ Bekor qilish", callback_data="pay_reply_cancel")])


# ===== Taqdimot =====
pres_cancel_button = Button(text="❌ Bekor qilish", callback_data="pres_cancel")


def pres_back_row(step):
    return [Button(text="⬅️ Orqaga", callback_data=f"pres_back:{step}"), pres_cancel_button]


pres_topic_menu = inline([pres_cancel_button])


def numbers_rows(numbers, prefix, per_row=5):
    buttons = [Button(text=str(n), callback_data=f"{prefix}{n}") for n in numbers]
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def pres_plans_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        *numbers_rows(range(PLAN_MIN, PLAN_MAX + 1), "pres_plans:"),
        pres_back_row("topic"),
    ])


def slide_options(plans):
    """Tanlash mumkin bo'lgan slaydlar soni: kamida reja + 4 (muqova, mundarija, reja, xulosa)."""
    return [n for n in SLIDE_OPTIONS if n >= plans + FIXED_SLIDES]


def priced_rows(options, unit, price, prefix):
    """«15 slayd · 7 500 so'm» ko'rinishidagi tugmalar, 2 tadan qatorda."""
    buttons = [Button(text=f"{n} {unit} · {money(price(n))}", callback_data=f"{prefix}{n}") for n in options]
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


def pres_slides_menu(plans):
    return InlineKeyboardMarkup(inline_keyboard=[
        *priced_rows(slide_options(plans), "slayd", presentation_price, "pres_slides:"),
        pres_back_row("plans"),
    ])


FORMAT_NAMES = {"pptx": "📊 PowerPoint (.pptx)", "docx": "📝 Word (.docx)", "pdf": "📕 PDF"}


def format_menu(prefix, native, back_row):
    return inline(
        [Button(text=FORMAT_NAMES[native], callback_data=f"{prefix}{native}"),
         Button(text=FORMAT_NAMES["pdf"], callback_data=f"{prefix}pdf")],
        back_row,
    )


def pres_lang_menu():
    return inline(
        [Button(text=name, callback_data=f"pres_lang:{key}") for key, name in LANGUAGES.items()],
        pres_back_row("slides"),
    )


def themes_rows(prefix, current=None, suffix=""):
    buttons = [
        Button(text=f"{'✅ ' if key == current else ''}{i}. {theme['name']}", callback_data=f"{prefix}{key}{suffix}")
        for i, (key, theme) in enumerate(THEMES.items(), 1)
    ]
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


def pres_theme_menu(current=None):
    return InlineKeyboardMarkup(inline_keyboard=[*themes_rows("pres_theme:", current), pres_back_row("lang")])


def pres_author_menu():
    return inline([Button(text="⏭ O'tkazib yuborish", callback_data="pres_author_skip")], pres_back_row("theme"))


def pay_rows(need):
    """Balans yetmaganda: shu buyurtma uchun to'lash (asosiy) yoki hisobni oldindan to'ldirish."""
    return [
        [Button(text=f"💳 To'lash va olish — {money(need)}", callback_data="order_pay")],
        [Button(text="➕ Hisobni to'ldirish", callback_data="wallet_topup")],
    ]


def pres_confirm_menu(price, need, back):
    if need > 0:
        return InlineKeyboardMarkup(inline_keyboard=[*pay_rows(need), pres_back_row(back)])
    if price:
        action = Button(text=f"✨ Yaratish — {money(price)}", callback_data="pres_go")
    else:
        action = Button(text="✨ Taqdimotni yaratish", callback_data="pres_go")
    return inline([action], pres_back_row(back))


def edit_row(kind, document_id):
    """Tayyor fayl ostidagi «✏️ Tahrirlash» — web ilovadagi muharrirni shu hujjat bilan ochadi.
    Ilova manzili yozilmagan bo'lsa (yoki hujjat ID'si yo'q) — tugma chiqmaydi."""
    if not WEBAPP_URL or not document_id:
        return []
    param = {"pres": "edit", "diplom": "diplomdoc", "diss": "dissdoc", "maqola": "article"}.get(kind, "paper")
    url = f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}{param}={document_id}"
    return [[Button(text="✏️ Tahrirlash", web_app=WebAppInfo(url=url))]]


def pres_result_menu(document_id=None):
    suffix = f":{document_id}" if document_id else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        *edit_row("pres", document_id),
        [Button(text="🎨 Boshqa dizaynda olish", callback_data=f"pres_redesign{suffix}")],
        [Button(text="📑 Yangi taqdimot", callback_data="pres")],
    ])


def pres_redesign_menu(current, document_id=None):
    suffix = f":{document_id}" if document_id else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        *themes_rows("pres_retheme:", current, suffix),
        [Button(text="⬅️ Orqaga", callback_data=f"pres_result{suffix}")],
    ])


def doc_result_menu(document_id):
    rows = edit_row("doc", document_id)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def file_menu(doc):
    """«📂 Hujjatlarim» dan qayta yuborilgan fayl ostidagi tugma."""
    rows = edit_row(doc["kind"], doc["id"])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


# ===== Referat / mustaqil ish / kurs ishi =====
doc_cancel_button = Button(text="❌ Bekor qilish", callback_data="doc_cancel")
doc_topic_menu = inline([doc_cancel_button])


def doc_back_row(step):
    return [Button(text="⬅️ Orqaga", callback_data=f"doc_back:{step}"), doc_cancel_button]


def doc_pages_menu(kind):
    return InlineKeyboardMarkup(inline_keyboard=[
        *priced_rows(PAGE_OPTIONS[kind], "bet", lambda n: document_price(kind, n), "doc_pages:"),
        doc_back_row("topic"),
    ])


def doc_lang_menu():
    return inline(
        [Button(text=name, callback_data=f"doc_lang:{key}") for key, name in LANGUAGES.items()],
        doc_back_row("pages"),
    )


def doc_confirm_menu(price, need, back):
    title_row = [Button(text="👤 Titulni tahrirlash", callback_data="titul")]
    if need > 0:
        return InlineKeyboardMarkup(inline_keyboard=[*pay_rows(need), title_row, doc_back_row(back)])
    if price:
        action = Button(text=f"✨ Yaratish — {money(price)}", callback_data="doc_go")
    else:
        action = Button(text="✨ Yaratish", callback_data="doc_go")
    return inline([action], title_row, doc_back_row(back))


def order_pay_menu(order_id):
    return inline(
        [Button(text="❌ Buyurtmani bekor qilish", callback_data=f"order_pay_cancel:{order_id}")],
    )


# ===== AI yordamchi =====
ai_cancel_button = Button(text="❌ Bekor qilish", callback_data="ai_cancel")
ai_topic_menu = inline([ai_cancel_button])
AI_KIND_BUTTONS = {"pres": "📊 Taqdimot", "referat": "📄 Referat", "mustaqil": "✍️ Mustaqil ish", "kurs": "📚 Kurs ishi"}


def ai_kind_menu():
    buttons = [Button(text=name, callback_data=f"ai_kind:{kind}") for kind, name in AI_KIND_BUTTONS.items()]
    return inline(buttons[:2], buttons[2:], [ai_cancel_button])


def ai_size_menu(rules):
    """Hajm tugmalari: chegaradagi qulay qiymatlar (standart — ⭐)."""
    low, high, default = rules["min"], rules["max"], rules["default"]
    values = sorted({low, default, high, *range(low - low % 5 + 5, high, 5)})
    buttons = [
        Button(text=f"{'⭐ ' if n == default else ''}{n}", callback_data=f"ai_size:{n}") for n in values if low <= n <= high
    ]
    return InlineKeyboardMarkup(inline_keyboard=[*[buttons[i:i + 4] for i in range(0, len(buttons), 4)], [ai_cancel_button]])


def ai_lang_menu(languages):
    return inline(
        [Button(text=name, callback_data=f"ai_lang:{key}") for key, name in languages.items()], [ai_cancel_button]
    )


# ===== Hujjatlarim =====
FILE_ICONS = {"pres": "📊", "referat": "📄", "mustaqil": "✍️", "kurs": "📚", "diplom": "🎓", "diss": "🔬",
              "maqola": "📝"}


def files_menu(docs):
    return InlineKeyboardMarkup(inline_keyboard=[
        [Button(text=f"{FILE_ICONS.get(d['kind'], '📄')} {d['title'][:45]}", callback_data=f"file:{d['id']}")]
        for d in docs
    ])


# ===== Titul ma'lumotlari =====
TITLE_FIELDS = {
    "university": "🏫 O'quv muassasasi",
    "faculty": "🏛 Fakultet / kafedra",
    "subject": "📘 Fan nomi",
    "student": "🎓 Talaba (F.I.Sh.)",
    "group": "👥 Guruh / sinf",
    "teacher": "👨‍🏫 O'qituvchi",
    "city": "📍 Shahar",
}


def title_menu(order_saved=False):
    buttons = [Button(text=label, callback_data=f"titul:{key}") for key, label in TITLE_FIELDS.items()]
    rows = [*[buttons[i:i + 2] for i in range(0, len(buttons), 2)],
            [Button(text="🗑 Hammasini tozalash", callback_data="titul_clear")]]
    if order_saved:  # buyurtma tasdiqlash qadamidan kelgan bo'lsa
        rows.append([Button(text="↩️ Buyurtmaga qaytish", callback_data="resume")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


title_back_menu = inline([Button(text="⬅️ Orqaga", callback_data="titul")])
