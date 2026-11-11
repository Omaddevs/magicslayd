"""Pastdagi doimiy menyu tugmalari.
Eng birinchi ulanadi — har qanday qadamda bosilsa ham mavzu/summa sifatida qabul qilinib ketmaydi."""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import SUPPORT_USERNAME
from handlers.account import account_show
from handlers.articles import article_start
from handlers.assistant import ai_start
from handlers.diploma import Diplom, diploma_start
from handlers.dissertation import Dissertatsiya, diss_start
from handlers.documents import doc_start, my_files, title_show
from handlers.presentation import designs, pres_command
from handlers.start import HELP_TEXT
from handlers.wallet import wallet_command
from keyboards import (
    BTN_ACCOUNT, BTN_AI, BTN_ARTICLE, BTN_BALANCE, BTN_DIPLOM, BTN_DISS, BTN_FILES, BTN_OTHER, BTN_PRES, BTN_TITLE, DOC_BUTTONS, other_menu,
)
from states import AdminPanel, AiAssistant, ChangePassword, EditTitle, Register

router = Router()


async def leave_text_input(handler, event, data):
    # Matn kutayotgan qadam (titul maydoni, AI yordamchi) yarim qolgan bo'lsa — menyu tugmasi bosilganda bekor
    # qilinadi, keyingi matn o'sha joyga yozilib ketmasin
    state: FSMContext = data["state"]
    current = await state.get_state()
    if current == EditTitle.value.state:
        await state.set_state(None)
    elif current and current.startswith(AiAssistant.__name__):
        await state.clear()
    elif current and current.startswith((Diplom.__name__, Dissertatsiya.__name__)):
        await state.set_state(None)  # ma'lumotlar bazada saqlangan — faqat matn kutish to'xtaydi
    elif current and current.startswith((Register.__name__, ChangePassword.__name__, AdminPanel.__name__)):
        await state.clear()  # keyingi matn parol sifatida qabul qilinib ketmasin
    return await handler(event, data)


router.message.middleware(leave_text_input)


async def other_services(message: Message):
    await message.answer(
        "🧰 <b>Boshqa xizmatlar</b>\n\nKerakli bo'limni tanlang 👇", reply_markup=other_menu(SUPPORT_USERNAME)
    )


router.message.register(pres_command, F.text == BTN_PRES)
router.message.register(doc_start, F.text.in_(DOC_BUTTONS))
router.message.register(my_files, F.text == BTN_FILES)
router.message.register(wallet_command, F.text == BTN_BALANCE)
router.message.register(title_show, F.text == BTN_TITLE)
router.message.register(other_services, F.text == BTN_OTHER)
router.message.register(ai_start, F.text == BTN_AI)
router.message.register(diploma_start, F.text == BTN_DIPLOM)
router.message.register(diss_start, F.text == BTN_DISS)
router.message.register(article_start, F.text == BTN_ARTICLE)


@router.message(F.text == BTN_ACCOUNT)
async def account_button(message: Message, state: FSMContext):
    await account_show(message, state)


@router.callback_query(F.data == "designs")
async def designs_button(callback: CallbackQuery, bot: Bot):
    await designs(callback.message, bot)
    await callback.answer()


@router.callback_query(F.data == "help")
async def help_button(callback: CallbackQuery):
    await callback.message.answer(HELP_TEXT)
    await callback.answer()
