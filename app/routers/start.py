from datetime import timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, LanguageEnum

router = Router()

# FIXED: раньше "новый пользователь" определялся как user.created_at == user.updated_at.
# Это хрупко: если поля выставляются БД отдельными вызовами func.now() с разной
# точностью (или есть малейшая задержка между INSERT и тем, как ORM прочитал значения),
# равенство может не выполниться для реально нового юзера, и он не увидит выбор языка.
# Используем небольшой допуск по времени вместо точного равенства.
NEW_USER_THRESHOLD = timedelta(seconds=1)


class StartState(StatesGroup):
    waiting_search = State()


# ──────────────────────────────────────────────
# Тексты
# ──────────────────────────────────────────────

WELCOME = {
    "uz": (
        "👋 Salom, <b>{name}</b>!\n\n"
        "📚 <b>KitobchiBot</b>ga xush kelibsiz — kitoblar izlash va yuklab olish boti.\n\n"
        "🔍 Kitob nomini yoki muallifni yozing:"
    ),
    "ru": (
        "👋 Привет, <b>{name}</b>!\n\n"
        "📚 Добро пожаловать в <b>KitobchiBot</b> — бот для поиска и скачивания книг.\n\n"
        "🔍 Напишите название книги или автора:"
    ),
    "en": (
        "👋 Hello, <b>{name}</b>!\n\n"
        "📚 Welcome to <b>KitobchiBot</b> — book search and download bot.\n\n"
        "🔍 Type a book title or author name:"
    ),
}

HELP_TEXT = {
    "uz": (
        "📖 <b>Qanday foydalanish:</b>\n\n"
        "• Kitob nomi yoki muallif yozing\n"
        "• Bot barcha manbalarda qidiradi\n"
        "• Kitobni yuklab oling va baholang ⭐\n\n"
        "🌐 /lang — tilni o'zgartirish"
    ),
    "ru": (
        "📖 <b>Как пользоваться:</b>\n\n"
        "• Напишите название книги или автора\n"
        "• Бот ищет во всех источниках\n"
        "• Скачайте книгу и оцените её ⭐\n\n"
        "🌐 /lang — сменить язык"
    ),
    "en": (
        "📖 <b>How to use:</b>\n\n"
        "• Type a book title or author\n"
        "• Bot searches all sources\n"
        "• Download and rate the book ⭐\n\n"
        "🌐 /lang — change language"
    ),
}


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="setlang:uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en"),
    ]])


# ──────────────────────────────────────────────
# /start — первый запуск
# ──────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, user: User, lang: str, state: FSMContext) -> None:
    await state.clear()

    # Если юзер новый — сначала выбор языка
    if (user.updated_at - user.created_at) < NEW_USER_THRESHOLD:
        await message.answer(
            "🌐 Tilni tanlang / Выберите язык / Choose language:",
            reply_markup=lang_keyboard(),
        )
        return

    name = message.from_user.first_name or "друг"
    await message.answer(
        WELCOME[lang].format(name=name),
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(StartState.waiting_search)


# ──────────────────────────────────────────────
# /lang — смена языка
# ──────────────────────────────────────────────

@router.message(F.text == "/lang")
async def cmd_lang(message: Message) -> None:
    await message.answer(
        "🌐 Tilni tanlang / Выберите язык / Choose language:",
        reply_markup=lang_keyboard(),
    )


@router.callback_query(F.data.startswith("setlang:"))
async def set_language(
    callback: CallbackQuery, session: AsyncSession, user: User, state: FSMContext
) -> None:
    lang = callback.data.split(":")[1]
    user.language = LanguageEnum(lang)
    await session.flush()

    name = callback.from_user.first_name or "друг"
    await callback.message.edit_text(
        WELCOME[lang].format(name=name),
        reply_markup=None,
    )
    await state.set_state(StartState.waiting_search)
    await callback.answer()


# ──────────────────────────────────────────────
# /help
# ──────────────────────────────────────────────

@router.message(F.text == "/help")
async def cmd_help(message: Message, lang: str) -> None:
    await message.answer(HELP_TEXT[lang]) 