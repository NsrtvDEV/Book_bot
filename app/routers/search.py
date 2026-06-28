import hashlib
import logging
from collections import OrderedDict

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, BookLanguageEnum, DownloadHistory, Rating, User
from app.services.aggregator import aggregator, UnifiedBook, SOURCE_EMOJI, detect_query_language

logger = logging.getLogger(__name__)
router = Router()

# ИЗМЕНЕНО: OrderedDict с ограничением размера вместо безграничного dict
_ext_cache: OrderedDict[str, UnifiedBook] = OrderedDict()
_EXT_CACHE_MAX = 2000


def _cache_external_book(book_hash: str, book: UnifiedBook) -> None:
    _ext_cache[book_hash] = book
    _ext_cache.move_to_end(book_hash)
    if len(_ext_cache) > _EXT_CACHE_MAX:
        _ext_cache.popitem(last=False)


def not_found_buttons(lang: str) -> InlineKeyboardMarkup:
    texts = {
        "uz": "📂 Kategoriyalar",
        "ru": "📂 Категории",
        "en": "📂 Categories",
    }
    t = texts.get(lang, texts["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data="show_categories")],
    ]) 


# ──────────────────────────────────────────────
# Поиск — любой текст
# ──────────────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_search(
    message: Message, state: FSMContext, session: AsyncSession, user: User, lang: str
) -> None:
    query = message.text.strip()
    if len(query) < 2:
        return

    wait_text = {
        "uz": "🔍 Barcha manbalarda qidirilmoqda...",
        "ru": "🔍 Ищу во всех источниках...",
        "en": "🔍 Searching all sources...",
    }

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        wait_msg = await message.answer(wait_text[lang])

        # 1. Своя БД — ищем по title И author, выводим СРАЗУ
        result = await session.execute(
            select(Book).where(
                Book.is_active == True,
                or_(
                    Book.title.ilike(f"%{query}%"),
                    Book.author.ilike(f"%{query}%"),
                )
            ).order_by(Book.download_count.desc()).limit(5)
        )
        local_books = result.scalars().all()

        try:
            await wait_msg.delete()
        except Exception:
            pass

        header = {
            "uz": f"📚 <b>{query}</b> bo'yicha natijalar:",
            "ru": f"📚 Результаты по запросу: <b>{query}</b>",
            "en": f"📚 Results for: <b>{query}</b>",
        }

        if local_books:
            await message.answer(header[lang])
            for book in local_books:
                await _send_local_card(message, book, lang)

        # 2. Внешние источники — догружаются следом
        query_lang = detect_query_language(query)
        external_books = await aggregator.search_all(query, lang=query_lang, limit_per_source=2)
        logger.info(f"[SEARCH] query={query!r} ui_lang={lang} query_lang={query_lang}")

    if not local_books and not external_books:
        not_found = {
            "uz": "😔 Hech narsa topilmadi. Boshqa so'z bilan qidiring.",
            "ru": "😔 Ничего не найдено. Попробуйте другой запрос.",
            "en": "😔 Nothing found. Try a different query.",
        }
        await message.answer(not_found[lang], reply_markup=not_found_buttons(lang))
        return

    if not local_books and external_books:
        await message.answer(header[lang])

    local_titles = {b.title.lower()[:20] for b in local_books}
    for book in external_books:
        if book.title.lower()[:20] not in local_titles:
            try:
                await _send_external_card(message, book, lang)
            except Exception as e:
                logger.error(f"Card error: {e}")


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
    buttons = [[InlineKeyboardButton(text=dl_text[lang], callback_data=f"download:{book.id}")]]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if book.cover_file_id:
        await message.answer_photo(photo=book.cover_file_id, caption=caption, reply_markup=markup)
    else:
        await message.answer(caption, reply_markup=markup)


async def _send_external_card(message: Message, book: UnifiedBook, lang: str) -> None:
    emoji = SOURCE_EMOJI.get(book.source, "📚")
    get_text = {"uz": "📥 Olish", "ru": "📥 Получить", "en": "📥 Get"}

    lines = [f"📖 <b>{book.title}</b>"]
    if book.author:
        lines.append(f"✍️ {book.author}")
    if book.year:
        lines.append(f"📅 {book.year}")
    lines.append(f"<i>{emoji} {book.source}</i>")
    caption = "\n".join(lines)

    book_hash = hashlib.md5(book.source_id.encode()).hexdigest()[:8]
    _cache_external_book(book_hash, book)  # ИЗМЕНЕНО: через LRU-кэш

    buttons = [[InlineKeyboardButton(
        text=f"{get_text[lang]} — {emoji} {book.source}",
        callback_data=f"ext:{book_hash}",
    )]]
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


# ──────────────────────────────────────────────
# Скачивание из своей БД
# ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("download:"))
async def download_local(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    book_id = int(callback.data.split(":")[1])
    book = await session.get(Book, book_id)

    if not book:
        await callback.answer("Книга не найдена.", show_alert=True)
        return

    await callback.message.answer_document(
        document=book.telegram_file_id,
        caption=f"📚 <b>{book.title}</b>\n✍️ {book.author or '—'}",
    )
    book.download_count += 1
    session.add(DownloadHistory(user_id=user.id, book_id=book.id))
    await session.flush()
    await _ask_rating(callback.message, book.id, lang)
    await callback.answer()


# ──────────────────────────────────────────────
# Скачивание из внешних источников
# ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("ext:"))
async def download_external(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    book_hash = callback.data.split(":")[1]
    book = _ext_cache.get(book_hash)

    if not book:
        await callback.answer(
            {"uz": "Qayta qidiring.", "ru": "Попробуйте поиск заново.", "en": "Please search again."}.get(lang),
            show_alert=True,
        )
        return

    existing = await session.execute(
        select(Book).where(
            func.lower(Book.title) == book.title.lower()
        )
    )
    existing_book = existing.scalar_one_or_none()

    if existing_book:
        await callback.message.answer_document(
            document=existing_book.telegram_file_id,
            caption=f"📚 <b>{existing_book.title}</b>\n✍️ {existing_book.author or '—'}",
        )
        existing_book.download_count += 1
        session.add(DownloadHistory(user_id=user.id, book_id=existing_book.id))
        await _ask_rating(callback.message, existing_book.id, lang)
        await callback.answer()
        return

    wait_text = {
        "uz": "⏳ Yuklanmoqda, kuting...",
        "ru": "⏳ Скачиваю, подождите...",
        "en": "⏳ Downloading, please wait...",
    }
    await callback.answer(wait_text[lang])

    async with ChatActionSender.upload_document(bot=callback.bot, chat_id=callback.message.chat.id):
        wait_msg = await callback.message.answer(wait_text[lang])
        file_bytes = await aggregator.download(book)

        try:
            await wait_msg.delete()
        except Exception:
            pass

        if not file_bytes:
            copyright_msg = aggregator.get_copyright_message(book.title, lang)
            await callback.message.answer(copyright_msg, disable_web_page_preview=True)
            return

        ext = ".epub" if book.source == "Standard Ebooks" else ".pdf"
        safe_title = "".join(c for c in book.title if c.isalnum() or c in " -_")[:50]
        file = BufferedInputFile(file_bytes, filename=f"{safe_title}{ext}")
        emoji = SOURCE_EMOJI.get(book.source, "📚")

        sent = await callback.message.answer_document(
            document=file,
            caption=(
                f"📚 <b>{book.title}</b>\n"
                f"✍️ {book.author or '—'}\n"
                f"<i>{emoji} {book.source}</i>"
            ),
        )

    check = await session.execute(
        select(Book).where(func.lower(Book.title) == book.title.lower())
    )
    existing_check = check.scalar_one_or_none()
    if not existing_check:
        new_book = Book(
            title=book.title,
            author=book.author,
            telegram_file_id=sent.document.file_id,
            file_size_kb=len(file_bytes) // 1024,
            language=BookLanguageEnum.RU if "ru" in (book.languages or []) else BookLanguageEnum.EN,
            download_count=1,
        )
        session.add(new_book)
        await session.flush()
        session.add(DownloadHistory(user_id=user.id, book_id=new_book.id))
        await _ask_rating(callback.message, new_book.id, lang)
    else:
        await _ask_rating(callback.message, existing_check.id, lang)


# ──────────────────────────────────────────────
# Оценка книги
# ──────────────────────────────────────────────

async def _ask_rating(message: Message, book_id: int, lang: str) -> None:
    text = {
        "uz": "⭐ Kitobni baholang:",
        "ru": "⭐ Оцените книгу:",
        "en": "⭐ Rate this book:",
    }
    buttons = [[
        InlineKeyboardButton(text="1⭐", callback_data=f"rate:{book_id}:1"),
        InlineKeyboardButton(text="2⭐", callback_data=f"rate:{book_id}:2"),
        InlineKeyboardButton(text="3⭐", callback_data=f"rate:{book_id}:3"),
        InlineKeyboardButton(text="4⭐", callback_data=f"rate:{book_id}:4"),
        InlineKeyboardButton(text="5⭐", callback_data=f"rate:{book_id}:5"),
    ]]
    await message.answer(text[lang], reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("rate:"))
async def rate_book(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    _, book_id_str, score_str = callback.data.split(":")
    book_id = int(book_id_str)
    score = int(score_str)

    book = await session.get(Book, book_id)
    if not book:
        await callback.answer("Книга не найдена.", show_alert=True)
        return

    existing = await session.execute(
        select(Rating).where(Rating.user_id == user.id, Rating.book_id == book_id)
    )
    rating = existing.scalar_one_or_none()

    if rating:
        old_score = rating.score
        rating.score = score
        total = book.avg_rating * book.rating_count - old_score + score
        book.avg_rating = round(total / book.rating_count, 2)
    else:
        session.add(Rating(user_id=user.id, book_id=book_id, score=score))
        total = book.avg_rating * book.rating_count + score
        book.rating_count += 1
        book.avg_rating = round(total / book.rating_count, 2)

    await session.flush()

    text = {
        "uz": f"✅ Rahmat! Sizning bahoyingiz: {'⭐' * score}",
        "ru": f"✅ Спасибо! Ваша оценка: {'⭐' * score}",
        "en": f"✅ Thanks! Your rating: {'⭐' * score}",
    }
    await callback.message.edit_text(text[lang])
    await callback.answer() 
    