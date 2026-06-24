from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from app.models import User

router = Router()

MAIN_MENU = {
    "uz": ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 Qidirish"),
                KeyboardButton(text="📂 Kategoriyalar"),
            ],
            [
                KeyboardButton(text="⭐ Hafta topi"),
                KeyboardButton(text="🏆 Bestsellerlar"),
            ],
            [KeyboardButton(text="🌐 Til")],
        ],
        resize_keyboard=True,
    ),
    "ru": ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="📂 Категории")],
            [
                KeyboardButton(text="⭐ Топ недели"),
                KeyboardButton(text="🏆 Бестселлеры"),
            ],
            [KeyboardButton(text="🌐 Язык")],
        ],
        resize_keyboard=True,
    ),
    "en": ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Search"), KeyboardButton(text="📂 Categories")],
            [
                KeyboardButton(text="⭐ Top of week"),
                KeyboardButton(text="🏆 Bestsellers"),
            ],
            [KeyboardButton(text="🌐 Language")],
        ],
        resize_keyboard=True,
    ),
}

WELCOME_TEXT = {
    "uz": "📚 <b>Book Bot</b>ga xush kelibsiz!\n\nQuyidagi bo'limlardan birini tanlang:",
    "ru": "📚 Добро пожаловать в <b>Book Bot</b>!\n\nВыберите раздел:",
    "en": "📚 Welcome to <b>Book Bot</b>!\n\nChoose a section:",
}


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, lang: str) -> None:
    await message.answer(
        WELCOME_TEXT[lang],
        reply_markup=MAIN_MENU[lang],
    )
