import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError

from config import ADMIN_ID, BOT_TOKEN, PAYMENT_CARDS
from handlers import (
    account, admin, admins, articles, assistant, diploma, dissertation, documents, menu, presentation, start, wallet,
    web,
)
from presentation.preview import themes_collage


async def set_commands(bot: Bot):
    # Hamma uchun oddiy menyu; har bir adminga (ega + u qo'shganlar) — admin buyruqlari (handlers/admins.py)
    await admins.setup_menus(bot)


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi! .env faylga bot tokenini yozing.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️ ANTHROPIC_API_KEY yozilmagan — taqdimot yaratilmaydi. .env faylga Claude API kalitini yozing.")
    if not ADMIN_ID or not PAYMENT_CARDS:
        print("⚠️ ADMIN_ID yoki PAYMENT_CARDS yozilmagan — hisobni to'ldirib bo'lmaydi. .env faylni to'ldiring.")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    # Tartib muhim: menyu tugmalari → buyruqlar → hamyon → hujjatlar → taqdimot qadamlari → qolgan hamma narsa
    dp.include_routers(
        menu.router, admins.router, admin.router, account.router, start.router, web.router, wallet.router, documents.router,
        articles.router, assistant.router, diploma.router,
        dissertation.router, presentation.router, start.fallback_router,
    )

    # Kompyuter yonganda internet (Wi-Fi) hali ulanmagan bo'lishi mumkin — ulanguncha kutamiz, qulab tushmaymiz
    for attempt in range(1, 61):
        try:
            await set_commands(bot)
            break
        except TelegramNetworkError:
            logging.warning("Telegram'ga ulanib bo'lmadi (internet?) — %s-urinish, 10 soniyadan keyin qayta", attempt)
            await asyncio.sleep(10)
    # Web ilova: sozlamalarni bazaga yozadi, menyu tugmasini qo'yadi va buyurtmalar navbatini ishga tushiradi
    await web.setup(bot)
    # Dizaynlar rasmi oldindan chiziladi — birinchi user kutib qolmasin
    await asyncio.to_thread(themes_collage)
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Har bir Claude/HTTP so'rovi uchun qator yozilmasin — serverda log toza tursin
    for noisy in ("httpx2", "httpx", "anthropic", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    asyncio.run(main())
