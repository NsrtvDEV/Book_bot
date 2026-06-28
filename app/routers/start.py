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
        "🌐 /lang — tilni o'zgartirish\n"
        "📂 /categories — kategoriyalar"
    ),
    "ru": (
        "📖 <b>Как пользоваться:</b>\n\n"
        "• Напишите название книги или автора\n"
        "• Бот ищет во всех источниках\n"
        "• Скачайте книгу и оцените её ⭐\n\n"
        "🌐 /lang — сменить язык\n"
        "📂 /categories — категории"
    ),
    "en": (
        "📖 <b>How to use:</b>\n\n"
        "• Type a book title or author\n"
        "• Bot searches all sources\n"
        "• Download and rate the book ⭐\n\n"
        "🌐 /lang — change language\n"
        "📂 /categories — categories"
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

    if user.created_at == user.updated_at:
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


# ──────────────────────────────────────────────
# /categories — категории
# ──────────────────────────────────────────────

@router.message(F.text == "/categories")
async def cmd_categories(message: Message, session: AsyncSession, lang: str) -> None:
    await _send_categories(message, session, lang)


@router.callback_query(F.data == "show_categories")
async def cb_show_categories(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    await _send_categories(callback.message, session, lang)
    await callback.answer()


async def _send_categories(message: Message, session: AsyncSession, lang: str) -> None:
    from sqlalchemy import select
    from app.models import Category

    result = await session.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order)
    )
    categories = result.scalars().all()

    if not categories:
        await message.answer("Категории пока не добавлены.")
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"{cat.emoji or ''} {cat.get_name(lang)}",
            callback_data=f"category:{cat.id}",
        )]
        for cat in categories
    ]
    text = {
        "uz": "📂 Kategoriyani tanlang:",
        "ru": "📂 Выберите категорию:",
        "en": "📂 Choose a category:",
    }
    await message.answer(
        text[lang],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )