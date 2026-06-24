import os

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, BookLanguageEnum, Category

router = Router()

ADMIN_IDS: list[int] = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


# ──────────────────────────────────────────────
# FSM States
# ──────────────────────────────────────────────


class UploadBook(StatesGroup):
    waiting_for_title = State()  # 1. Название
    waiting_for_category = State()  # 2. Категория
    waiting_for_author = State()  # 3. Автор
    waiting_for_language = State()  # 4. Язык книги
    waiting_for_file = State()  # 5. PDF файл
    waiting_for_cover = State()  # 6. Обложка
    waiting_for_description = State()  # 7. Описание


# ──────────────────────────────────────────────
# Шаг 1 — Название
# ──────────────────────────────────────────────


@router.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "📝 <b>Шаг 1/7</b>\n\nВведите название книги:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(UploadBook.waiting_for_title)


# ──────────────────────────────────────────────
# Шаг 2 — Категория
# ──────────────────────────────────────────────


@router.message(UploadBook.waiting_for_title, F.text)
async def receive_title(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.update_data(title=message.text.strip())

    result = await session.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order)
    )
    categories = result.scalars().all()

    if not categories:
        await state.update_data(category_id=None)
        await ask_author(message, state)
        return

    buttons = [
        [KeyboardButton(text=f"{cat.emoji or ''} {cat.name_ru}")] for cat in categories
    ]
    buttons.append([KeyboardButton(text="⏭ Пропустить")])

    await state.update_data(
        categories={f"{cat.emoji or ''} {cat.name_ru}": cat.id for cat in categories}
    )
    await message.answer(
        "📂 <b>Шаг 2/7</b>\n\nВыберите категорию:",
        reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True),
    )
    await state.set_state(UploadBook.waiting_for_category)


# ──────────────────────────────────────────────
# Шаг 3 — Автор
# ──────────────────────────────────────────────


@router.message(UploadBook.waiting_for_category, F.text)
async def receive_category(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    categories = data.get("categories", {})

    if message.text == "⏭ Пропустить":
        await state.update_data(category_id=None)
    else:
        category_id = categories.get(message.text)
        await state.update_data(category_id=category_id)

    await ask_author(message, state)


async def ask_author(message: Message, state: FSMContext) -> None:
    await message.answer(
        "✍️ <b>Шаг 3/7</b>\n\nВведите автора книги (или /skip):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(UploadBook.waiting_for_author)


# ──────────────────────────────────────────────
# Шаг 4 — Язык
# ──────────────────────────────────────────────


@router.message(UploadBook.waiting_for_author, F.text)
async def receive_author(message: Message, state: FSMContext) -> None:
    author = None if message.text == "/skip" else message.text.strip()
    await state.update_data(author=author)

    buttons = [
        [KeyboardButton(text="🇺🇿 O'zbek"), KeyboardButton(text="🇷🇺 Русский")],
        [KeyboardButton(text="🇬🇧 English"), KeyboardButton(text="🌐 Все языки")],
    ]
    await message.answer(
        "🌐 <b>Шаг 4/7</b>\n\nЯзык книги:",
        reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True),
    )
    await state.set_state(UploadBook.waiting_for_language)


# ──────────────────────────────────────────────
# Шаг 5 — PDF файл
# ──────────────────────────────────────────────

LANG_MAP = {
    "🇺🇿 O'zbek": BookLanguageEnum.UZ,
    "🇷🇺 Русский": BookLanguageEnum.RU,
    "🇬🇧 English": BookLanguageEnum.EN,
    "🌐 Все языки": BookLanguageEnum.ALL,
}


@router.message(UploadBook.waiting_for_language, F.text)
async def receive_language(message: Message, state: FSMContext) -> None:
    lang = LANG_MAP.get(message.text, BookLanguageEnum.RU)
    await state.update_data(language=lang)

    await message.answer(
        "📎 <b>Шаг 5/7</b>\n\nОтправьте PDF файл книги:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(UploadBook.waiting_for_file)


# ──────────────────────────────────────────────
# Шаг 6 — Обложка
# ──────────────────────────────────────────────


@router.message(UploadBook.waiting_for_file, F.document)
async def receive_file(message: Message, state: FSMContext) -> None:
    doc = message.document
    if not doc.file_name.lower().endswith(".pdf"):
        await message.answer("❌ Только PDF файлы. Попробуйте снова:")
        return

    await state.update_data(
        telegram_file_id=doc.file_id,
        file_size_kb=doc.file_size // 1024 if doc.file_size else None,
    )
    await message.answer(
        "🖼 <b>Шаг 6/7</b>\n\nОтправьте обложку книги (фото) или /skip:",
    )
    await state.set_state(UploadBook.waiting_for_cover)


@router.message(UploadBook.waiting_for_file)
async def wrong_file(message: Message) -> None:
    await message.answer("❌ Отправьте PDF файл, не текст и не фото.")


# ──────────────────────────────────────────────
# Шаг 7 — Описание
# ──────────────────────────────────────────────


@router.message(UploadBook.waiting_for_cover, F.photo)
async def receive_cover(message: Message, state: FSMContext) -> None:
    await state.update_data(cover_file_id=message.photo[-1].file_id)
    await ask_description(message, state)


@router.message(UploadBook.waiting_for_cover, F.text)
async def skip_cover(message: Message, state: FSMContext) -> None:
    await state.update_data(cover_file_id=None)
    await ask_description(message, state)


async def ask_description(message: Message, state: FSMContext) -> None:
    await message.answer(
        "📝 <b>Шаг 7/7</b>\n\nВведите описание книги (или /skip):",
    )
    await state.set_state(UploadBook.waiting_for_description)


# ──────────────────────────────────────────────
# Финал — сохранение в БД
# ──────────────────────────────────────────────


@router.message(UploadBook.waiting_for_description, F.text)
async def receive_description(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    description = None if message.text == "/skip" else message.text.strip()

    data = await state.get_data()
    await state.clear()

    book = Book(
        title=data["title"],
        author=data.get("author"),
        telegram_file_id=data["telegram_file_id"],
        file_size_kb=data.get("file_size_kb"),
        cover_file_id=data.get("cover_file_id"),
        language=data.get("language", BookLanguageEnum.RU),
        category_id=data.get("category_id"),
        description_ru=description,
    )
    session.add(book)
    await session.flush()

    data_book = await state.get_data() if False else data
    category_name = "—"
    if book.category_id:
        cat = await session.get(Category, book.category_id)
        category_name = cat.name_ru if cat else "—"

    await message.answer(
        f"✅ <b>Книга успешно добавлена!</b>\n\n"
        f"📚 Название: <b>{book.title}</b>\n"
        f"✍️ Автор: {book.author or '—'}\n"
        f"📂 Категория: {category_name}\n"
        f"🌐 Язык: {book.language}\n"
        f"🆔 ID: {book.id}",
    )
