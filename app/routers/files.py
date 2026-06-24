from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, DownloadHistory, Rating, User

router = Router()


@router.callback_query(F.data.startswith("book:"))
async def show_book_detail(
    callback: CallbackQuery, session: AsyncSession, lang: str
) -> None:
    book_id = int(callback.data.split(":")[1])
    book = await session.get(Book, book_id)

    if not book:
        await callback.answer("Книга не найдена.", show_alert=True)
        return

    description = book.get_description(lang) or ""
    lang_label = {"uz": "📖 Til", "ru": "📖 Язык", "en": "📖 Language"}
    book_lang_label = {
        "uz": "O'zbek",
        "ru": "Русский",
        "en": "English",
        "all": "UZ/RU/EN",
    }

    text = (
        f"📚 <b>{book.title}</b>\n"
        f"✍️ {book.author or '—'}\n"
        f"{lang_label[lang]}: {book_lang_label.get(book.language, book.language)}\n"
        f"⭐ {book.avg_rating:.1f} ({book.rating_count} votes)\n"
        f"📥 {book.download_count} downloads\n\n"
        f"{description}"
    )

    download_text = {"uz": "📥 Yuklab olish", "ru": "📥 Скачать", "en": "📥 Download"}
    rate_text = {"uz": "⭐ Baholash", "ru": "⭐ Оценить", "en": "⭐ Rate"}

    buttons = [
        [
            InlineKeyboardButton(
                text=download_text[lang], callback_data=f"download:{book_id}"
            )
        ],
        [
            InlineKeyboardButton(text="1⭐", callback_data=f"rate:{book_id}:1"),
            InlineKeyboardButton(text="2⭐", callback_data=f"rate:{book_id}:2"),
            InlineKeyboardButton(text="3⭐", callback_data=f"rate:{book_id}:3"),
            InlineKeyboardButton(text="4⭐", callback_data=f"rate:{book_id}:4"),
            InlineKeyboardButton(text="5⭐", callback_data=f"rate:{book_id}:5"),
        ],
    ]

    if book.cover_file_id:
        await callback.message.answer_photo(
            photo=book.cover_file_id,
            caption=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("download:"))
async def send_book_file(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    book_id = int(callback.data.split(":")[1])
    book = await session.get(Book, book_id)

    if not book or not book.telegram_file_id:
        await callback.answer("Файл не найден.", show_alert=True)
        return

    await callback.message.answer_document(
        document=book.telegram_file_id,
        caption=f"📚 <b>{book.title}</b>\n✍️ {book.author or '—'}",
    )

    # Увеличиваем счётчик скачиваний
    book.download_count += 1

    # Сохраняем в историю
    history = DownloadHistory(user_id=user.id, book_id=book.id)
    session.add(history)
    await session.flush()

    await callback.answer()


@router.callback_query(F.data.startswith("rate:"))
async def rate_book(
    callback: CallbackQuery, session: AsyncSession, user: User, lang: str
) -> None:
    from sqlalchemy import select

    _, book_id_str, score_str = callback.data.split(":")
    book_id = int(book_id_str)
    score = int(score_str)

    book = await session.get(Book, book_id)
    if not book:
        await callback.answer("Книга не найдена.", show_alert=True)
        return

    # Проверяем — уже оценил?
    existing = await session.execute(
        select(Rating).where(Rating.user_id == user.id, Rating.book_id == book_id)
    )
    rating = existing.scalar_one_or_none()

    if rating:
        old_score = rating.score
        rating.score = score
        # Пересчитываем avg
        total = book.avg_rating * book.rating_count - old_score + score
        book.avg_rating = total / book.rating_count
    else:
        rating = Rating(user_id=user.id, book_id=book_id, score=score)
        session.add(rating)
        # Пересчитываем avg
        total = book.avg_rating * book.rating_count + score
        book.rating_count += 1
        book.avg_rating = total / book.rating_count

    await session.flush()

    text = {
        "uz": f"✅ Bahoyingiz qabul qilindi: {score}⭐",
        "ru": f"✅ Ваша оценка принята: {score}⭐",
        "en": f"✅ Your rating accepted: {score}⭐",
    }
    await callback.answer(text[lang], show_alert=True)
