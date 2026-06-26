import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, BookLanguageEnum, DownloadHistory, User
from app.services.aggregator import aggregator, UnifiedBook

logger = logging.getLogger(__name__)
router = Router()

SOURCE_EMOJI = {
    "Open Library": "📚",
    "Project Gutenberg": "📖",
    "Standard Ebooks": "✨",
}


class SearchState(StatesGroup):
    waiting_query = State()


# ──────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────

@router.message(F.text.in_(["🔍 Qidirish", "🔍 Поиск", "🔍 Search"]))
async def ask_search_query(message: Message, state: FSMContext, lang: str) -> None:
    text = {
        "uz": "🔍 Kitob nomi yoki muallifni kiriting:",
        "ru": "🔍 Введите название книги или автора:",
        "en": "🔍 Enter book title or author:",
    }
    await message.answer(text[lang])
    await state.set_state(SearchState.waiting_query)


@router.message(SearchState.waiting_query, F.text)
async def handle_search(message: Message, state: FSMContext, session: AsyncSession, lang: str) -> None:
    await state.clear()
    query = message.text.strip()

    wait_text = {"uz": "🔍 Qidirilmoqda...", "ru": "🔍 Ищу во всех источниках...", "en": "🔍 Searching all sources..."}
    wait_msg = await message.answer(wait_text[lang])

    try:
        result = await session.execute(
            select(Book).where(
                Book.is_active == True,
                (Book.title.ilike(f"%{query}%")) | (Book.author.ilike(f"%{query}%"))
            ).limit(3)
        )
        local_books = result.scalars().all()
        logger.warning(f"[DEBUG] local_books: {len(local_books)}")

        external_books = await aggregator.search_all(query, limit_per_source=2)
        logger.warning(f"[DEBUG] external_books: {len(external_books)}")

    except Exception as e:
        logger.error(f"[DEBUG] search crashed: {e}", exc_info=True)
        await wait_msg.delete()
        await message.answer("Ошибка поиска.")
        return

    await wait_msg.delete()

    if not local_books and not external_books:
        not_found = {
            "uz": "😔 Hech narsa topilmadi.",
            "ru": "😔 Ничего не найдено. Попробуйте другой запрос.",
            "en": "😔 Nothing found. Try a different query.",
        }
        await message.answer(not_found[lang])
        return

    header = {
        "uz": f"📚 <b>{query}</b> bo'yicha natijalar:",
        "ru": f"📚 Результаты по запросу: <b>{query}</b>",
        "en": f"📚 Results for: <b>{query}</b>",
    }
    await message.answer(header[lang])

    for book in local_books:
        await _send_local_card(message, book, lang)

    local_titles = {b.title.lower() for b in local_books}
    for book in external_books:
        if book.title.lower() not in local_titles:
            try:
                await _send_external_card(message, book, lang)
            except Exception as e:
                logger.error(f"[DEBUG] _send_external_card crashed: {e}", exc_info=True)

# ──────────────────────────────────────────────
# Карточки
# ──────────────────────────────────────────────

async def _send_local_card(message: Message, book: Book, lang: str) -> None:
    dl_text = {"uz": "📥 Yuklab olish", "ru": "📥 Скачать", "en": "📥 Download"}
    caption = (
        f"📖 <b>{book.title}</b>\n"
        f"✍️ {book.author or '—'}\n"
        f"⭐ {book.avg_rating:.1f}  📥 {book.download_count}\n"
        f"<i>🏠 В нашей библиотеке</i>"
    )
    buttons = [
        [InlineKeyboardButton(text=dl_text[lang], callback_data=f"download:{book.id}")],
        [
            InlineKeyboardButton(text="1⭐", callback_data=f"rate:{book.id}:1"),
            InlineKeyboardButton(text="2⭐", callback_data=f"rate:{book.id}:2"),
            InlineKeyboardButton(text="3⭐", callback_data=f"rate:{book.id}:3"),
            InlineKeyboardButton(text="4⭐", callback_data=f"rate:{book.id}:4"),
            InlineKeyboardButton(text="5⭐", callback_data=f"rate:{book.id}:5"),
        ],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if book.cover_file_id:
        await message.answer_photo(photo=book.cover_file_id, caption=caption, reply_markup=markup)
    else:
        await message.answer(caption, reply_markup=markup)


async def _send_external_card(message: Message, book: UnifiedBook, lang: str) -> None:
    emoji = SOURCE_EMOJI.get(book.source, "📚")
    get_text = {"uz": "📥 Olish", "ru": "📥 Получить", "en": "📥 Get"}

    caption = (
        f"📖 <b>{book.title}</b>\n"
        f"✍️ {book.author or '—'}\n"
        f"{f'📅 {book.year}' if book.year else ''}\n"
        f"<i>{emoji} {book.source}</i>"
    ).strip()

    import json, hashlib
    book_hash = hashlib.md5(f"{book.source_id}".encode()).hexdigest()[:8]

    buttons = [[InlineKeyboardButton(
        text=f"{get_text[lang]} ({book.source})",
        callback_data=f"ext:{book.source[:2]}:{book_hash}",
    )]]

    # Кэшируем данные книги в FSM не нужно — используем глобальный кэш
    _ext_cache[book_hash] = book

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if book.cover_url:
        try:
            cover = await aggregator.get_cover_bytes(book)
            if cover:
                photo = BufferedInputFile(cover, filename="cover.jpg")
                await message.answer_photo(photo=photo, caption=caption, reply_markup=markup)
                return
        except Exception:
            pass

    await message.answer(caption, reply_markup=markup)


# Простой in-memory кэш для книг между поиском и скачиванием
_ext_cache: dict[str, UnifiedBook] = {}


# ──────────────────────────────────────────────
# Скачивание внешних книг
# ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("ext:"))
async def download_external(callback: CallbackQuery, session: AsyncSession, user: User, lang: str) -> None:
    parts = callback.data.split(":")
    book_hash = parts[2]
    book = _ext_cache.get(book_hash)

    if not book:
        await callback.answer("Попробуйте поиск заново.", show_alert=True)
        return

    # Уже есть в нашей БД?
    existing = await session.execute(select(Book).where(Book.title == book.title))
    existing_book = existing.scalar_one_or_none()
    if existing_book:
        await callback.message.answer_document(
            document=existing_book.telegram_file_id,
            caption=f"📚 <b>{existing_book.title}</b>\n✍️ {existing_book.author or '—'}",
        )
        existing_book.download_count += 1
        session.add(DownloadHistory(user_id=user.id, book_id=existing_book.id))
        await callback.answer()
        return

    wait_text = {
        "uz": "⏳ Yuklanmoqda...",
        "ru": "⏳ Скачиваю, подождите...",
        "en": "⏳ Downloading, please wait...",
    }
    await callback.answer(wait_text[lang])
    wait_msg = await callback.message.answer(wait_text[lang])

    file_bytes = await aggregator.download(book)

    if not file_bytes:
        await wait_msg.delete()
        err = {"uz": "❌ Fayl topilmadi.", "ru": "❌ Файл не найден.", "en": "❌ File not found."}
        await callback.message.answer(err[lang])
        return

    ext = ".epub" if book.source == "Standard Ebooks" else ".pdf"
    file = BufferedInputFile(file_bytes, filename=f"{book.title}{ext}")
    emoji = SOURCE_EMOJI.get(book.source, "📚")

    sent = await callback.message.answer_document(
        document=file,
        caption=f"📚 <b>{book.title}</b>\n✍️ {book.author or '—'}\n<i>{emoji} {book.source}</i>",
    )
    await wait_msg.delete()

    # Сохраняем в БД
    new_book = Book(
        title=book.title,
        author=book.author,
        telegram_file_id=sent.document.file_id,
        file_size_kb=len(file_bytes) // 1024,
        language=BookLanguageEnum.EN,
        download_count=1,
    )
    session.add(new_book)
    await session.flush()
    session.add(DownloadHistory(user_id=user.id, book_id=new_book.id))

    _ext_cache.pop(book_hash, None) 