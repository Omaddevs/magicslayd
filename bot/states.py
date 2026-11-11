from aiogram.fsm.state import State, StatesGroup


class MakePresentation(StatesGroup):
    topic = State()
    plans = State()
    slides = State()
    lang = State()
    theme = State()
    author = State()
    format = State()
    confirm = State()


class MakeDocument(StatesGroup):
    topic = State()
    pages = State()
    lang = State()
    format = State()
    confirm = State()


class MakeArticle(StatesGroup):
    type = State()
    topic = State()
    lang = State()
    size = State()
    words = State()  # «Maxsus» hajm — so'zlar sonini yozadi
    extra = State()
    notes = State()  # qo'shimcha talablarni yozadi
    confirm = State()


class EditTitle(StatesGroup):
    value = State()


class TopUp(StatesGroup):
    amount = State()
    check = State()


class AdminReply(StatesGroup):
    text = State()


class AdminPanel(StatesGroup):
    broadcast = State()  # hamma userlarga xabar (nusxa) — xabarni kutyapti
    forward = State()  # forward qilinadigan xabarni kutyapti
    find = State()  # user qidirish
    amount = State()  # balansni o'zgartirish summasi
    dm = State()  # bitta userga xabar
    credit = State()  # Claude hisobi balansi (USD)


class ManageAdmins(StatesGroup):
    pick = State()  # ega yangi adminni tanlayapti (kontakt tanlash tugmasi yoki Telegram ID)


class Register(StatesGroup):
    phone = State()
    password = State()
    confirm = State()


class ChangePassword(StatesGroup):
    password = State()
    confirm = State()


class AiAssistant(StatesGroup):
    kind = State()
    topic = State()
    size = State()
    lang = State()
