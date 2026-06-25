from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, Category, User, WeeklyTop, LanguageEnum
from app.routers.start import MAIN_MENU, WELCOME_TEXT

router = Router()


MENU_BUTTONS = [
    "📂 Kategoriyalar",
    "📂 Категории",
    "📂 Categories",
    "⭐ Hafta topi",
    "⭐ Топ недели",
    "⭐ Top of week",
    "🏆 Bestsellerlar",
    "🏆 Бестселлеры",
    "🏆 Bestsellers",
    "🔍 Qidirish",
    "🔍 Поиск",
    "🔍 Search",
    "🌐 Til",
    "🌐 Язык",
    "🌐 Language",
]


# ──────────────────────────────────────────────
# Категории
# ──────────────────────────────────────────────


@router.message(F.text.in_(["📂 Kategoriyalar", "📂 Категории", "📂 Categories"]))
async def show_categories(message: Message, session: AsyncSession, lang: str) -> None:
    result = await session.execute(
        select(Category)
        .where(Category.is_active == True, Category.parent_id.is_(None))
        .order_by(Category.sort_order)
    )
    categories = result.scalars().all()

    if not categories:
        await message.answer("Категории пока не добавлены.")
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{cat.emoji or ''} {cat.get_name(lang)}",
                callback_data=f"category:{cat.id}",
            )
        ]
        for cat in categories
    ]
    text = {
        "uz": "📂 Kategoriyani tanlang:",
        "ru": "📂 Выберите категорию:",
        "en": "📂 Choose a category:",
    }
    await message.answer(
        text[lang], reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("category:"))
async def show_books_by_category(
    callback: CallbackQuery, session: AsyncSession, lang: str
) -> None:
    category_id = int(callback.data.split(":")[1])

    # проверяем — есть ли подкатегории
    result = await session.execute(
        select(Category)
        .where(Category.parent_id == category_id, Category.is_active == True)
        .order_by(Category.sort_order)
    )
    subcategories = result.scalars().all()

    if subcategories:
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"{sub.emoji or ''} {sub.get_name(lang)}",
                    callback_data=f"category:{sub.id}",
                )
            ]
            for sub in subcategories
        ]
        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="category_back")]
        )
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        await callback.answer()
        return

    # подкатегорий нет — показываем книги
    result = await session.execute(
        select(Book)
        .where(Book.category_id == category_id, Book.is_active == True)
        .order_by(Book.avg_rating.desc())
        .limit(20)
    )
    books = result.scalars().all()

    if not books:
        await callback.answer("Книги не найдены.", show_alert=True)
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"📖 {book.title}  ⭐{book.avg_rating:.1f}",
                callback_data=f"book:{book.id}",
            )
        ]
        for book in books
    ]
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data == "category_back")
async def category_back(
    callback: CallbackQuery, session: AsyncSession, lang: str
) -> None:
    result = await session.execute(
        select(Category)
        .where(Category.is_active == True, Category.parent_id.is_(None))
        .order_by(Category.sort_order)
    )
    categories = result.scalars().all()

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{cat.emoji or ''} {cat.get_name(lang)}",
                callback_data=f"category:{cat.id}",
            )
        ]
        for cat in categories
    ]
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


# ──────────────────────────────────────────────
# Топ недели
# ──────────────────────────────────────────────


@router.message(F.text.in_(["⭐ Hafta topi", "⭐ Топ недели", "⭐ Top of week"]))
async def show_weekly_top(message: Message, session: AsyncSession, lang: str) -> None:
    today = datetime.utcnow()
    week_start = (today - timedelta(days=today.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result = await session.execute(
        select(WeeklyTop)
        .where(WeeklyTop.week_start == week_start)
        .order_by(WeeklyTop.rank)
        .limit(10)
    )
    tops = result.scalars().all()

    if not tops:
        text = {
            "uz": "Bu hafta uchun top hali shakllanmagan.",
            "ru": "Топ недели пока не сформирован.",
            "en": "Top of the week is not ready yet.",
        }
        await message.answer(text[lang])
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for top in tops:
        medal = medals[top.rank - 1] if top.rank <= 3 else f"{top.rank}."
        book = await session.get(Book, top.book_id)
        if book:
            lines.append(
                f"{medal} <b>{book.title}</b> — ⭐{top.avg_score:.1f} ({top.vote_count} votes)"
            )

    header = {
        "uz": "⭐ Bu haftaning eng yaxshi kitoblari:",
        "ru": "⭐ Лучшие книги этой недели:",
        "en": "⭐ Best books this week:",
    }
    await message.answer(header[lang] + "\n\n" + "\n".join(lines))


# ──────────────────────────────────────────────
# Бестселлеры
# ──────────────────────────────────────────────


@router.message(F.text.in_(["🏆 Bestsellerlar", "🏆 Бестселлеры", "🏆 Bestsellers"]))
async def show_bestsellers(message: Message, session: AsyncSession, lang: str) -> None:
    result = await session.execute(
        select(Book)
        .where(Book.is_bestseller == True, Book.is_active == True)
        .order_by(Book.avg_rating.desc())
        .limit(20)
    )
    books = result.scalars().all()

    if not books:
        await message.answer("Бестселлеры пока не добавлены.")
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"🏆 {book.title}  ⭐{book.avg_rating:.1f}",
                callback_data=f"book:{book.id}",
            )
        ]
        for book in books
    ]
    header = {
        "uz": "🏆 Jahon bestsellerlari:",
        "ru": "🏆 Мировые бестселлеры:",
        "en": "🏆 World bestsellers:",
    }
    await message.answer(
        header[lang], reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


# ──────────────────────────────────────────────
# Поиск
# ──────────────────────────────────────────────


@router.message(F.text.in_(["🔍 Qidirish", "🔍 Поиск", "🔍 Search"]))
async def ask_search_query(message: Message, lang: str) -> None:
    text = {
        "uz": "🔍 Kitob nomi yoki muallifni kiriting:",
        "ru": "🔍 Введите название книги или автора:",
        "en": "🔍 Enter book title or author:",
    }
    await message.answer(text[lang])


@router.message(
    StateFilter(None),
    F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_BUTTONS),
)
async def search_books(message: Message, session: AsyncSession, lang: str) -> None:
    query = f"%{message.text}%"
    result = await session.execute(
        select(Book)
        .where(
            Book.is_active == True,
            (Book.title.ilike(query)) | (Book.author.ilike(query)),
        )
        .limit(10)
    )
    books = result.scalars().all()

    if not books:
        text = {
            "uz": "😔 Hech narsa topilmadi.",
            "ru": "😔 Ничего не найдено.",
            "en": "😔 Nothing found.",
        }
        await message.answer(text[lang])
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"📖 {book.title} — {book.author or ''}  ⭐{book.avg_rating:.1f}",
                callback_data=f"book:{book.id}",
            )
        ]
        for book in books
    ]
    text = {
        "uz": f"📚 Topildi: {len(books)} ta kitob",
        "ru": f"📚 Найдено: {len(books)} книг",
        "en": f"📚 Found: {len(books)} books",
    }
    await message.answer(
        text[lang], reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


# ──────────────────────────────────────────────
# Язык
# ──────────────────────────────────────────────


@router.message(F.text.in_(["🌐 Til", "🌐 Язык", "🌐 Language"]))
async def show_language_menu(message: Message) -> None:
    buttons = [
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        ]
    ]
    await message.answer(
        "Tilni tanlang / Выберите язык / Choose language:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("lang:"))
async def set_language(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    lang = callback.data.split(":")[1]
    user.language = LanguageEnum(lang)
    await session.flush()
    await callback.message.answer(WELCOME_TEXT[lang], reply_markup=MAIN_MENU[lang])
    await callback.answer()
