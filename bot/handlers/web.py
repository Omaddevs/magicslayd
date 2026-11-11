"""Web ilova (slayd-web) bilan bog'lanish.
Ilova (Node.js server) shu botning bazasiga yozadi: buyurtmalar web_orders jadvaliga tushadi,
bot ularni navbat bilan bajaradi va tayyor faylni userning Telegram chatiga yuboradi.
Narxlar, dizaynlar va tillar ilovaga meta jadvali orqali beriladi — yagona manba shu bot."""
import asyncio
import html
import json
import logging
import shutil
import time
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, MenuButtonWebApp, Message, WebAppInfo

from admins import OWNER_ID, Can, has_perm, is_owner
from config import (
    ARTICLE_PRICE_MIN, ARTICLE_PRICE_PER_100, ARTICLE_WORDS_MAX, ARTICLE_WORDS_MIN, DATA_DIR,
    DIPLOM_PAGE_OPTIONS, DIPLOM_PAGE_PRICE, DIPLOM_PAGES_MAX, DIPLOM_PAGES_MIN, DISS_PAGE_PRICE,
    DISS_PAGES_MAX, DISS_PAGES_MIN, DISS_TYPES, FIXED_SLIDES,
    PAGE_OPTIONS, PAGE_PRICE, PAGE_RANGE, PAYMENT_CARDS, PENDING_MAX, PLAN_MAX, PLAN_MIN, SLIDE_OPTIONS, SLIDE_PRICE,
    SUPPORT_USERNAME, TOPUP_MAX, TOPUP_MIN, TOPUP_OPTIONS, WEBAPP_URL, image_count, money,
)
from articles import storage as article_storage
from articles.ai import generate_article
from articles.export import build as build_article
from articles.model import SIZES as ARTICLE_SIZES
from diploma import service as diploma_service
from dissertation import service as diss_service
from assistant.service import AssistantError, public_settings, validate
from assistant.service import run as assistant_run
from converter import PDF_AVAILABLE, ConvertError, to_pdf
from database import (
    add_material, add_payment, add_presentation, change_balance, claim_web_order, delete_material,
    expire_unpaid_orders, finish_web_order, get_document, get_payment, get_title, get_web_order, last_materials,
    refund_stale_holds, release_paid_order, set_meta, set_web_order_charged, stuck_web_orders,
)
from documents.ai import generate_document
from documents.builder import build_docx
from documents.importer import import_paper
from documents.storage import cleanup_old_papers, has_paper, load_paper, save_paper, save_paper_file
from handlers.articles import deliver_article, notify_failed as notify_article_failed, price_for_article
from handlers.broadcast import broadcast_worker
from handlers.documents import DOC_NAMES, deliver_document, doc_price
from handlers.presentation import ERRORS, ai_slots, alert_admin, generating, price_for, remember_deck, send_deck
from handlers.wallet import apply_review, order_label, send_payment_to_admin, support_line, topup_error
from presentation.ai import LANGUAGES, generate_content
from presentation.builder import build_pptx
from presentation.importer import ImportError_, import_file
from presentation.storage import cleanup_old_decks, load_deck, read_source, save_file, save_project
from diploma.designs import public_designs
from presentation.themes import THEME_CATEGORIES, THEMES

router = Router()

POLL_SECONDS = 2  # yangi buyurtmalar shu oraliqda tekshiriladi
RECEIPTS_DIR = DATA_DIR / "receipts"  # saytdan yuklangan cheklar (bot qabul qilgach o'chiriladi)
AI_DIR = DATA_DIR / "ai"  # AI yordamchi natijalari sayt uchun (24 soat saqlanadi)
assistant_slots = asyncio.Semaphore(4)  # bir vaqtda nechta AI yordamchi so'rovi bajariladi
MATERIAL_KINDS = {"pres": "Taqdimot", "referat": "Referat", "mustaqil": "Mustaqil ish", "kurs": "Kurs ishi",
                  "shablon": "Shablon"}
_tasks = set()  # bajarilayotgan buyurtmalar (garbage collector o'chirib yubormasligi uchun)


# ===== Ishga tushirish =====
async def setup(bot: Bot):
    me = await bot.me()
    set_meta("web_config", json.dumps({
        "bot_username": me.username,
        "support": SUPPORT_USERNAME,
        "pdf": PDF_AVAILABLE,
        "slides": {"options": list(SLIDE_OPTIONS), "price": SLIDE_PRICE, "fixed": FIXED_SLIDES,
                   "plan_min": PLAN_MIN, "plan_max": PLAN_MAX},
        "pages": {kind: list(options) for kind, options in PAGE_OPTIONS.items()},
        "page_range": {kind: list(bounds) for kind, bounds in PAGE_RANGE.items()},  # o'zi yozadigan betlar oralig'i
        "page_price": PAGE_PRICE,
        "diploma": {"page_price": DIPLOM_PAGE_PRICE, "min": DIPLOM_PAGES_MIN, "max": DIPLOM_PAGES_MAX,
                    "options": list(DIPLOM_PAGE_OPTIONS)},
        "dissertation": {"page_price": DISS_PAGE_PRICE, "min": DISS_PAGES_MIN, "max": DISS_PAGES_MAX,
                         "types": {k: {**v, "options": list(v["options"])} for k, v in DISS_TYPES.items()}},
        "languages": LANGUAGES,
        "themes": THEMES,
        "theme_categories": THEME_CATEGORIES,  # «Shablonlar» sahifasidagi filtr va bo'limlar
        "doc_designs": public_designs(),  # diplom ishi / dissertatsiya rasmiylashtirish dizaynlari
        "ai": public_settings(),  # AI yordamchi: ish turlari, hajm chegaralari, tillar, limitlar
        # Maqola: hajm variantlari va narx (so'zlar soniga qarab) — bot bilan bir xil qoida (config.article_price)
        "article": {"sizes": {k: list(v) for k, v in ARTICLE_SIZES.items()}, "words_min": ARTICLE_WORDS_MIN,
                    "words_max": ARTICLE_WORDS_MAX, "price_per_100": ARTICLE_PRICE_PER_100,
                    "price_min": ARTICLE_PRICE_MIN},
        # Hisobni to'ldirish: karta, summa chegaralari (bot bilan bir xil qoidalar)
        "payment": {
            "enabled": bool(PAYMENT_CARDS and OWNER_ID),
            "cards": [{"number": number, "holder": holder} for number, holder in PAYMENT_CARDS],
            "min": TOPUP_MIN, "max": TOPUP_MAX, "options": list(TOPUP_OPTIONS), "pending_max": PENDING_MAX,
        },
    }, ensure_ascii=False))

    if WEBAPP_URL:
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Ilova", web_app=WebAppInfo(url=WEBAPP_URL)))
        except TelegramAPIError:
            # Manzil noto'g'ri bo'lsa ham bot ishlashda davom etsin
            logging.exception("Ilova menyu tugmasini qo'yib bo'lmadi (WEBAPP_URL https bo'lishi kerak)")

    # Bot to'xtab qolganda yarim yo'lda qolgan buyurtmalar — pul qaytariladi
    for order in stuck_web_orders():
        reason = "Bot qayta ishga tushdi. Qayta urinib ko'ring."
        if order["charged"]:
            change_balance(order["user_id"], order["charged"], "refund", f"Web buyurtma #{order['id']}")
            reason = "Bot qayta ishga tushdi. Pul hisobingizga qaytarildi, qayta urinib ko'ring."
        finish_web_order(order["id"], error=reason)

    # Bot chatidagi buyurtmalar (taqdimot, referat ...) — bot to'xtaganda yetkazilmagan bo'lsa, pul qaytariladi
    for user_id, amount in refund_stale_holds():
        logging.warning("Yetkazilmagan buyurtma puli qaytarildi: user %s, %s", user_id, amount)
        with suppress(TelegramAPIError):
            await bot.send_message(
                user_id, f"😕 Bot qayta ishga tushgani uchun buyurtmangiz yakunlanmadi.\n"
                         f"💰 {money(amount)} hisobingizga qaytarildi — qayta urinib ko'ring.")

    _tasks.add(asyncio.create_task(orders_worker(bot)))
    _tasks.add(asyncio.create_task(cleanup_worker()))
    # Admin ilovadan yuborgan bildirishnomalar — barcha userlarga Telegram orqali
    _tasks.add(asyncio.create_task(broadcast_worker(bot)))


async def cleanup_worker():
    """Har soatda: cheki 24 soat ichida kelmagan buyurtmalarni bekor qiladi.
    Kuniga bir marta: eski taqdimot loyihalarini o'chiradi (disk to'lib qolmasligi uchun)."""
    hours = 0
    while True:
        try:
            expired = expire_unpaid_orders()
            if expired:
                logging.info("To'lovi kelmagan buyurtmalar bekor qilindi: %s ta", expired)
            await asyncio.to_thread(cleanup_ai_results)
            if hours % 24 == 0:
                removed = (await asyncio.to_thread(cleanup_old_decks) + await asyncio.to_thread(cleanup_old_papers)
                           + await asyncio.to_thread(article_storage.cleanup_old_articles))
                if removed:
                    logging.info("Eski taqdimot loyihalari o'chirildi: %s ta", removed)
        except Exception:
            logging.exception("Tozalashda xato")
        hours += 1
        await asyncio.sleep(3600)


# ===== Buyurtmalar navbati =====
async def orders_worker(bot: Bot):
    while True:
        try:
            order = claim_web_order(generating)
        except Exception:
            logging.exception("Web buyurtmani olishda xato")
            order = None
        if order is None:
            await asyncio.sleep(POLL_SECONDS)
            continue
        if order["kind"] == "edit":
            task = asyncio.create_task(run_edit(order))
        elif order["kind"] == "import":
            task = asyncio.create_task(run_import(bot, order))
        elif order["kind"] == "receipt":
            task = asyncio.create_task(run_receipt(bot, order))
        elif order["kind"] == "pay_review":
            task = asyncio.create_task(run_pay_review(bot, order))
        elif order["kind"] == "admins":
            task = asyncio.create_task(run_admins(bot, order))
        elif order["kind"] == "ai":
            task = asyncio.create_task(run_ai(order))
        elif order["kind"] == "diplom":
            task = asyncio.create_task(run_diploma(bot, order))
        elif order["kind"] == "diss":
            task = asyncio.create_task(run_dissertation(bot, order))
        else:
            # claim va shu qator orasida await yo'q — user bir vaqtda ikki buyurtma bera olmaydi
            generating.add(order["user_id"])
            task = asyncio.create_task(run_order(bot, order))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


async def run_pay_review(bot: Bot, order):
    """Web admin paneldan chekni tasdiqlash / rad etish — botdagi tugma bilan bir xil yo'l."""
    params = json.loads(order["params"])
    try:
        if not has_perm(order["user_id"], "payments"):
            finish_web_order(order["id"], error="Faqat admin uchun.")
            return
        ok, text, _ = await apply_review(bot, int(params["payment_id"]), bool(params["approve"]), order["user_id"])
        finish_web_order(order["id"], error=None if ok else text)
    except Exception:
        logging.exception("Web: to'lovni ko'rib chiqishda xato (#%s)", order["id"])
        finish_web_order(order["id"], error="To'lovni ko'rib chiqishda xato.")


async def run_admins(bot: Bot, order):
    """Web admin paneldan admin qo'shish / o'chirish — faqat bot egasi (botdagi /adminlar bilan bir xil yo'l)."""
    from handlers.admins import AdminError, grant, revoke, update_perms  # kech import: handlers.admins → keyboards

    params = json.loads(order["params"])
    try:
        if not is_owner(order["user_id"]):
            raise AdminError("Adminlarni faqat bot egasi boshqaradi.")
        target = int(params["user_id"])
        action = params.get("action")
        if action == "add":
            await grant(bot, order["user_id"], target)
        elif action == "remove":
            await revoke(bot, order["user_id"], target)
        elif action == "perms":
            await update_perms(bot, order["user_id"], target, list(params.get("perms") or []))
        else:
            raise AdminError("Noma'lum amal.")
        finish_web_order(order["id"])
    except AdminError as e:
        finish_web_order(order["id"], error=str(e))
    except Exception:
        logging.exception("Web: adminlarni boshqarishda xato (#%s)", order["id"])
        finish_web_order(order["id"], error="Kutilmagan xato yuz berdi.")


async def run_edit(order):
    """Muharrirda saqlangan taqdimot yoki ishni AI'siz qayta yig'adi (pul yechilmaydi, chatga yuborilmaydi)."""
    params = json.loads(order["params"])
    document_id = params["document_id"]
    if await asyncio.to_thread(article_storage.has_article, document_id):
        await run_article_export(order, document_id, "pdf" if params.get("fmt") == "pdf" else "docx")
        return
    if await asyncio.to_thread(has_paper, document_id):
        await run_paper_edit(order, document_id)
        return
    try:
        loaded = await asyncio.to_thread(load_deck, document_id)
        if loaded is None or loaded[0].get("user_id") != order["user_id"]:
            finish_web_order(order["id"], error="Taqdimot loyihasi topilmadi.")
            return
        project, content = loaded
        pptx = await asyncio.to_thread(build_pptx, content, project["theme"], project["lang"], project.get("author"))
        await asyncio.to_thread(save_file, document_id, pptx)
        finish_web_order(order["id"], document_id=document_id)
    except Exception:
        logging.exception("Taqdimotni qayta yig'ishda xato")
        finish_web_order(order["id"], error="Taqdimotni saqlab bo'lmadi. Rasm yoki videoni almashtirib ko'ring.")


async def run_paper_edit(order, document_id):
    """Referat / mustaqil ish / kurs ishi: muharrirdagi matn va titul bilan faylni qayta yasaydi."""
    try:
        loaded = await asyncio.to_thread(load_paper, document_id)
        if loaded is None or loaded[0].get("user_id") != order["user_id"]:
            finish_web_order(order["id"], error="Hujjat loyihasi topilmadi.")
            return
        project, content = loaded
        fmt = project.get("fmt", "docx")
        file = await asyncio.to_thread(build_docx, content, project["kind"], project["lang"], project.get("title_page"))
        if fmt == "pdf":
            file = await to_pdf(file, "docx")
        await asyncio.to_thread(save_paper_file, document_id, file, fmt)
        finish_web_order(order["id"], document_id=document_id)
    except ConvertError as e:
        finish_web_order(order["id"], error=str(e))
    except Exception:
        logging.exception("Hujjatni qayta yig'ishda xato")
        finish_web_order(order["id"], error="Hujjatni saqlab bo'lmadi. Rasmni almashtirib, qayta urinib ko'ring.")


async def run_import(bot: Bot, order):
    """Eski taqdimot yoki ish (yoki saytdan yuklangan PPTX/PDF) dan muharrir loyihasini tiklaydi (AI'siz, bepul)."""
    document_id = json.loads(order["params"])["document_id"]
    try:
        document = get_document(document_id, order["user_id"])
        if not document:
            finish_web_order(order["id"], error="Fayl topilmadi.")
            return
        if document["kind"] != "pres":
            # Referat / mustaqil ish / kurs ishi — DOCX yoki PDF dan
            data = (await bot.download(document["file_id"])).getvalue()
            content, title_page, lang, fmt = await asyncio.to_thread(import_paper, data, document["title"])
            # PDF qayta yig'ish LibreOffice talab qiladi — bo'lmasa saqlangandan keyin Word bo'ladi
            fmt = fmt if fmt == "docx" or PDF_AVAILABLE else "docx"
            await asyncio.to_thread(save_paper, document_id, order["user_id"], document["kind"], lang, fmt,
                                    title_page, content, None, True)
            finish_web_order(order["id"], document_id=document_id)
            return
        data = await asyncio.to_thread(read_source, document_id)
        if data is None:
            data = (await bot.download(document["file_id"])).getvalue()
        project, media = await asyncio.to_thread(import_file, data)
        await asyncio.to_thread(save_project, document_id, order["user_id"], project, media)
        finish_web_order(order["id"], document_id=document_id)
    except ImportError_ as e:
        finish_web_order(order["id"], error=str(e))
    except TelegramAPIError as e:
        logging.warning("Import uchun faylni yuklab bo'lmadi: %s", e)
        reason = ("Fayl 20 MB dan katta — uni saytdagi «Fayl yuklash» orqali qayta yuklang."
                  if "too big" in str(e) else "Faylni Telegram'dan olib bo'lmadi. Qayta urinib ko'ring.")
        finish_web_order(order["id"], error=reason)
    except Exception:
        logging.exception("Faylni import qilishda xato")
        finish_web_order(order["id"], error="Faylni o'qib bo'lmadi. U buzilgan bo'lishi mumkin.")


async def run_ai(order):
    """AI yordamchi (sayt): limit va log yozuvi sayt tomonida ochilgan (request_id). Natija va fayllar
    ai/<vazifa_id>/ ga yoziladi — sayt ularni ko'rsatadi va yuklab beradi (24 soatdan keyin o'chiriladi)."""
    params = json.loads(order["params"])
    try:
        async with assistant_slots:
            clean = validate(params)
            result, files = await assistant_run(f"tg:{order['user_id']}", "web", clean, params["request_id"])
        folder = AI_DIR / str(order["id"])
        folder.mkdir(parents=True, exist_ok=True)
        for file in files:
            (folder / f"file.{file['ext']}").write_bytes(file["data"])
        meta = {"result": result, "files": [{"ext": f["ext"], "name": f["name"]} for f in files]}
        (folder / "result.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        finish_web_order(order["id"])
    except AssistantError as e:
        finish_web_order(order["id"], error=str(e))
    except Exception:
        logging.exception("AI yordamchi natijasini saqlab bo'lmadi")
        finish_web_order(order["id"], error="Faylni tayyorlab bo'lmadi. Iltimos, qayta urinib ko'ring.")


async def run_diploma(bot: Bot, order):
    """Diplom ishi amali (sayt): reja, tasdiqlash (to'lov), qismni yozish, tahrirlash, manbalar, eksport.
    Mantiq botdagi bilan bir xil — diploma/service.py."""
    params = json.loads(order["params"])
    try:
        document_id = await diploma_service.run_job(bot, order["user_id"], params)
        finish_web_order(order["id"], document_id=document_id)
    except diploma_service.DiplomaError as e:
        finish_web_order(order["id"], error=str(e))
    except TelegramAPIError as e:
        logging.warning("Diplom faylini yuborib bo'lmadi: %s", e)
        finish_web_order(order["id"], error="Bot sizga fayl yubora olmadi. Botga kirib /start bosing va qayta urinib ko'ring.")
    except Exception:
        logging.exception("Diplom ishi amalida xato")
        finish_web_order(order["id"], error="Kutilmagan xato yuz berdi. Ishingiz saqlangan — qayta urinib ko'ring.")


async def run_dissertation(bot: Bot, order):
    """Dissertatsiya amali (sayt) — mantiq botdagi bilan bir xil: dissertation/service.py."""
    try:
        document_id = await diss_service.run_job(bot, order["user_id"], json.loads(order["params"]))
        finish_web_order(order["id"], document_id=document_id)
    except diss_service.DissError as e:
        finish_web_order(order["id"], error=str(e))
    except TelegramAPIError as e:
        logging.warning("Dissertatsiya faylini yuborib bo'lmadi: %s", e)
        finish_web_order(order["id"], error="Bot sizga fayl yubora olmadi. Botga kirib /start bosing va qayta urinib ko'ring.")
    except Exception:
        logging.exception("Dissertatsiya amalida xato")
        finish_web_order(order["id"], error="Kutilmagan xato yuz berdi. Ishingiz saqlangan — qayta urinib ko'ring.")


def cleanup_ai_results(hours=24):
    """Sayt uchun tayyorlangan AI yordamchi fayllari — muddati o'tgach o'chiriladi."""
    if not AI_DIR.exists():
        return 0
    limit, removed = time.time() - hours * 3600, 0
    for folder in AI_DIR.iterdir():
        if folder.is_dir() and folder.stat().st_mtime < limit:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


async def run_receipt(bot: Bot, order):
    """Saytdan yuborilgan to'lov cheki. Bot chatidagi to'lov bilan bir xil yo'l: chek userning chatiga
    «qabul qilindi» bo'lib tushadi (shu orqali Telegram'ga yuklanadi), so'ng adminga tekshiruvga ketadi."""
    params = json.loads(order["params"])
    user_id, amount = order["user_id"], params["amount"]
    paid_order = params.get("order_id")  # buyurtma uchun to'lov bo'lsa — tasdiqlangach o'sha buyurtma boshlanadi
    file = RECEIPTS_DIR / params["file"]

    def fail(reason):
        finish_web_order(order["id"], error=reason)
        if paid_order:
            release_paid_order(paid_order, False, reason)

    try:
        error = topup_error(user_id)
        if error or not file.is_file():
            fail(error or "Chek fayli topilmadi. Qayta yuklang.")
            return
        upload = BufferedInputFile(file.read_bytes(), filename=params["file"])
        after = (f"📦 Buyurtma: {order_label(get_web_order(paid_order))}\n\n"
                 "Admin tasdiqlagach, buyurtmangiz <b>avtomatik tayyorlanib</b>, shu chatga yuboriladi ⏳"
                 if paid_order else "Admin tekshirgach, summa hamyoningizga tushadi va sizga xabar beramiz ⏳")
        caption = (
            "🧾 <b>Chek qabul qilindi</b> (ilova orqali)\n\n"
            f"💰 Summa: <b>{money(amount)}</b>\n"
            f"{after}"
            f"{support_line()}"
        )
        if params["type"] == "photo":
            sent = await bot.send_photo(user_id, upload, caption=caption)
            file_id = sent.photo[-1].file_id
        else:
            sent = await bot.send_document(user_id, upload, caption=caption)
            file_id = sent.document.file_id
        payment_id = add_payment(user_id, amount, file_id, params["type"], paid_order)
        await send_payment_to_admin(bot, get_payment(payment_id))
        finish_web_order(order["id"], document_id=payment_id)  # document_id — bu yerda to'lov raqami
    except TelegramAPIError as e:
        logging.warning("Chekni yuborib bo'lmadi: %s", e)
        fail("Bot sizga xabar yubora olmadi. Botga kirib /start bosing va qayta yuboring.")
    except Exception:
        logging.exception("Saytdan kelgan chekni qabul qilishda xato")
        fail("Chekni qabul qilib bo'lmadi. Qayta urinib ko'ring.")
    finally:
        file.unlink(missing_ok=True)


async def run_order(bot: Bot, order):
    user_id, kind = order["user_id"], order["kind"]
    charged = 0  # yechilgan, lekin hali qaytarilmagan / yetkazilmagan summa
    try:
        params = json.loads(order["params"])
        if kind == "pres":
            price, note = price_for(user_id, params["slides"]), f"Taqdimot: {params['topic'][:40]}"
        elif kind == "maqola":
            price, note = price_for_article(user_id, params["words"]), f"Maqola: {params['topic'][:40]}"
        else:
            price = doc_price(user_id, kind, params["pages"])
            note = f"{DOC_NAMES[kind].split(' ', 1)[1]}: {params['topic'][:40]}"
        # Narx bot tomonida qayta hisoblanadi — ilovadagi hisob faqat ko'rsatish uchun
        if price and not change_balance(user_id, -price, "charge", note):
            finish_web_order(order["id"], error="Balans yetarli emas. Avval hisobni to'ldiring.")
            return
        charged = price
        set_web_order_charged(order["id"], price)

        try:
            make = {"pres": make_presentation, "maqola": make_article}.get(kind, make_document)
            document_id = await make(bot, user_id, kind, params)
        except Exception as e:
            if isinstance(e, ERRORS):
                reason = str(e)
                await alert_admin(bot, e)
            else:
                logging.exception("Web buyurtmani bajarishda xato")
                reason = "Kutilmagan xato yuz berdi."
            refunded = bool(price) and change_balance(user_id, price, "refund", f"Xato: {params['topic'][:40]}")
            charged = 0
            reason += f" {money(price)} hisobingizga qaytarildi." if refunded else ""
            finish_web_order(order["id"], error=reason)
            if params.get("source") == "bot":  # bot chatidan berilgan buyurtma — sababini chatga yozamiz
                await notify_article_failed(bot, user_id, params, reason)
            return

        charged = 0  # fayl yetkazildi
        finish_web_order(order["id"], document_id=document_id)
        if kind == "pres":
            add_presentation(user_id, params["topic"], params["slides"], price)
    except Exception:
        # Kutilmagan xato (buzilgan buyurtma ma'lumoti, baza xatosi ...) — buyurtma «tayyorlanmoqda» da qotib qolmasin
        logging.exception("Web buyurtma #%s da kutilmagan xato", order["id"])
        refunded = bool(charged) and change_balance(user_id, charged, "refund", f"Web buyurtma #{order['id']}")
        with suppress(Exception):
            finish_web_order(order["id"], error="Kutilmagan xato yuz berdi."
                             + (f" {money(charged)} hisobingizga qaytarildi." if refunded else ""))
    finally:
        generating.discard(user_id)


async def make_presentation(bot: Bot, user_id, kind, p):
    async with ai_slots:
        content, images = await generate_content(
            p["topic"], p["plans"], p["slides"], p["lang"], image_count(p["slides"]), p["theme"]
        )
    deck = {
        "content": content, "theme": p["theme"], "lang": p["lang"], "author": p.get("author") or "",
        "slides": p["slides"], "fmt": p.get("fmt", "pptx"), "images": images,
    }
    document_id = await send_deck(bot, user_id, deck)
    remember_deck(user_id, deck)  # chatdagi «Boshqa dizaynda olish» tugmasi ham ishlaydi
    return document_id


async def make_article(bot: Bot, user_id, kind, p):
    """Maqola (bot chati va web ilova uchun umumiy): AI yozadi → saqlanadi → Word fayl chatga yuboriladi."""
    async with ai_slots:
        result = await generate_article(p, int(p["words"]))
    return await deliver_article(bot, user_id, p, result)


async def run_article_export(order, document_id, fmt):
    """Muharrirdagi JORIY versiyadan Word yoki PDF yasaydi (AI'siz, bepul) — sayt shu faylni beradi."""
    try:
        project = await asyncio.to_thread(article_storage.load, document_id)
        if project is None or project.get("user_id") != order["user_id"]:
            finish_web_order(order["id"], error="Maqola topilmadi.")
            return
        data = await asyncio.to_thread(build_article, project, article_storage.media_reader(document_id), fmt,
                                       project.get("author", ""))
        await asyncio.to_thread(article_storage.save_export, document_id, fmt, data, project["rev"])
        finish_web_order(order["id"], document_id=document_id)
    except Exception:
        logging.exception("Maqola faylini yasashda xato")
        finish_web_order(order["id"], error="Faylni tayyorlab bo'lmadi. Rasmni almashtirib, qayta urinib ko'ring.")


async def make_document(bot: Bot, user_id, kind, p):
    async with ai_slots:
        content = await generate_document(kind, p["topic"], p["lang"], p["pages"])
    return await deliver_document(bot, user_id, content, kind, p["lang"], p.get("fmt", "docx"), get_title(user_id))


# ===== «Ommabop materiallar» (admin) =====
MATERIAL_USAGE = (
    "📚 <b>Ommabop materiallar</b> — ilovaning bosh sahifasida chiqadi.\n\n"
    "Qo'shish: faylga <b>reply</b> qilib yozing:\n"
    "<code>/ommabop kurs 36 Marketing asoslari kurs ishi</code>\n"
    f"Turlari: {', '.join(MATERIAL_KINDS)}\n\n"
    "O'chirish: <code>/ommabop_del 12</code>"
)


@router.message(Command("ommabop"), Can("broadcast"))
async def material_add(message: Message, command: CommandObject):
    document = message.reply_to_message.document if message.reply_to_message else None
    parts = (command.args or "").split(maxsplit=2)
    if not document or len(parts) < 3 or parts[0] not in MATERIAL_KINDS or not parts[1].isdecimal():
        recent = "\n".join(
            f"#{m['id']} {html.escape(m['title'][:50])} — {MATERIAL_KINDS.get(m['kind'], m['kind'])}, "
            f"⬇️ {m['downloads']}"
            for m in last_materials()
        )
        await message.answer(MATERIAL_USAGE + (f"\n\n🕘 <b>Oxirgilari</b>\n{recent}" if recent else ""))
        return
    name = document.file_name or ""
    file_type = name.rsplit(".", 1)[1].lower() if "." in name else "docx"
    kind, pages, title = parts[0], int(parts[1]), parts[2][:150]
    material_id = add_material(kind, title, pages, document.file_id, file_type)
    await message.answer(f"✅ Qo'shildi: #{material_id} {html.escape(title)} ({MATERIAL_KINDS[kind]}, {pages})")


@router.message(Command("ommabop_del"), Can("broadcast"))
async def material_delete(message: Message, command: CommandObject):
    arg = (command.args or "").strip().lstrip("#")
    if not arg.isdecimal():
        await message.answer(MATERIAL_USAGE)
        return
    await message.answer("🗑 O'chirildi." if delete_material(int(arg)) else "Bunday material topilmadi.")
