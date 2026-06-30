"""
Агрегатор всех источников книг.
Ищет параллельно по всем источникам в зависимости от языка запроса.

Источники:
  🇬🇧 EN: Open Library, Project Gutenberg, Standard Ebooks
  🇷🇺 RU: Archive.org (rus), ImWerden (русская классика)
  🇺🇿 UZ: Archive.org (uzb)
  🌐 ALL: все источники
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.open_library import open_library
from app.services.gutenberg import gutenberg
from app.services.standard_ebooks import standard_ebooks
from app.services.archive_uz import archive_uz
from app.services.imwerden import imwerden

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 49 * 1024 * 1024  # 49 MB — лимит Telegram


def normalize_title(title: str) -> str:
    """Нормализует название книги для сравнения/дедупликации."""
    return re.sub(r"\s+", " ", title or "").strip().lower()


def _stringify_author(author) -> Optional[str]:
    """
    FIXED: некоторые источники (например, Gutenberg при нескольких авторах)
    могут отдавать author как list, а не str. UnifiedBook.author объявлен
    как Optional[str], но без приведения типа на границе list просачивался
    дальше и ронял .strip() в дедупе с AttributeError.
    """
    if not author:
        return None
    if isinstance(author, (list, tuple, set)):
        return ", ".join(str(a) for a in author if a) or None
    return str(author)


def _author_sort_key(author) -> str:
    """Защитная версия приведения author к строке для использования как ключ дедупа."""
    return (_stringify_author(author) or "").strip().lower()


@dataclass
class UnifiedBook:
    title: str
    author: Optional[str]
    cover_url: Optional[str]
    source: str
    source_id: str
    source_ids: list[str] = field(default_factory=list)
    year: Optional[int] = None
    description: Optional[str] = None
    languages: list[str] = field(default_factory=list)
    is_copyrighted: bool = False


SOURCE_EMOJI = {
    "Open Library": "📚",
    "Project Gutenberg": "📖",
    "Standard Ebooks": "✨",
    "Archive.org (UZ)": "🇺🇿",
    "Archive.org (RU)": "🇷🇺",
    "ImWerden (Русская классика)": "📜",
}

COPYRIGHT_MSG = {
    "uz": (
        "⚠️ <b>{title}</b> kitobi mualliflik huquqi bilan himoyalangan.\n\n"
        "Bu kitobni qonuniy ravishda quyidagi saytlardan sotib olishingiz mumkin:\n"
        "📌 <a href='https://www.litres.ru/'>LitRes</a>\n"
        "📌 <a href='https://www.amazon.com/'>Amazon Kindle</a>\n"
        "📌 <a href='https://books.google.com/'>Google Books</a>"
    ),
    "ru": (
        "⚠️ Книга <b>{title}</b> защищена авторским правом.\n\n"
        "Вы можете приобрести её легально на:\n"
        "📌 <a href='https://www.litres.ru/'>ЛитРес</a>\n"
        "📌 <a href='https://www.amazon.com/'>Amazon Kindle</a>\n"
        "📌 <a href='https://books.google.com/'>Google Books</a>"
    ),
    "en": (
        "⚠️ The book <b>{title}</b> is protected by copyright.\n\n"
        "You can purchase it legally at:\n"
        "📌 <a href='https://www.amazon.com/'>Amazon Kindle</a>\n"
        "📌 <a href='https://books.google.com/'>Google Books</a>\n"
        "📌 <a href='https://www.litres.ru/'>LitRes</a>"
    ),
}

# FIXED: раньше на ЛЮБУЮ неудачу скачивания (сеть, таймаут, файл слишком большой,
# временно недоступен) показывалось сообщение про копирайт и ссылку купить книгу —
# даже для источников, которые по определению public domain (Gutenberg,
# Standard Ebooks, Archive.org, ImWerden). Теперь для них отдельное,
# не вводящее в заблуждение сообщение.
TECH_ERROR_MSG = {
    "uz": (
        "⚠️ <b>{title}</b> kitobini hozir yuklab bo'lmadi.\n"
        "Birozdan keyin qayta urinib ko'ring."
    ),
    "ru": (
        "⚠️ Не удалось скачать книгу <b>{title}</b> прямо сейчас.\n"
        "Попробуйте ещё раз чуть позже."
    ),
    "en": (
        "⚠️ Couldn't download <b>{title}</b> right now.\n"
        "Please try again in a bit."
    ),
}

# Источники, где отказ в скачивании реально может означать copyright/lending-only
# (Open Library хранит и DRM-защищённые книги, доступные только на чтение онлайн).
_COPYRIGHT_CAPABLE_SOURCES = {"Open Library"}


def detect_query_language(query: str) -> str:
    """Определяет язык поискового запроса (не язык интерфейса пользователя)."""
    q = query.lower()

    # Кириллица → русский
    if any('\u0400' <= c <= '\u04FF' for c in q):
        return "ru"

    # Узбекские маркеры (латиница)
    uzbek_markers = [
        "o'", "g'", "o`", "g`",
        "toxtaboyev", "to'xtaboyev", "qodirov", "qodiriy", "navoiy",
        "toshmatov", "xolmatov", "yusupov", "abdullayev", "mirzayev",
        "ergashev", "nazarov", "tursunov", "haydarov", "rajabov",
        "cho'lpon", "cholpon", "aytmatov", "tohir", "malik", "oybek",
        "kitob", "roman", "qissa", "hikoya", "she'r",
        "o'zbek", "uzbek", "toshkent", "samarqand", "buxoro",
        "xudoyberdi", "muxtorjon", "asliddin", "nodir", "javlon",
        "sherzod", "dilnoza", "malika", "aziza", "nodira",
        "qodir", "kamoliddin", "islom", "ibrohim", "sulaymon",
        "mo'tabar", "zulfiya", "feruza", "shahnoza", "munira",
    ]
    if any(m in q for m in uzbek_markers):
        return "uz"

    return "en"


class BookAggregator:

    async def search_all(
        self, query: str, lang: str = "all", limit_per_source: int = 2
    ) -> list[UnifiedBook]:
        """
        Параллельный поиск во всех источниках.
        lang: 'uz', 'ru', 'en', 'all'
        """
        tasks = []

        if lang in ("en", "all"):
            tasks += [
                self._search_open_library(query, limit_per_source),
                self._search_gutenberg(query, limit_per_source),
                self._search_standard_ebooks(query, limit_per_source),
            ]

        if lang in ("ru", "all"):
            tasks += [
                self._search_archive_ru(query, limit_per_source),
                self._search_imwerden(query, limit_per_source),
            ]

        if lang in ("uz", "all"):
            tasks += [
                self._search_archive_uz(query, limit_per_source),
                self._search_archive_ru(query, limit_per_source),
                self._search_open_library(query, limit_per_source),
                self._search_gutenberg(query, limit_per_source),
            ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        unified = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Source search error: {result}")
                continue
            unified.extend(result)

        # FIXED: раньше дедуп шёл по title.lower()[:30] — два разных тома одной
        # серии ("Война и мир. Том 1" / "Том 2") могли слипнуться в одну запись.
        # Теперь сравниваем нормализованную пару (title, author) целиком.
        seen = set()
        deduped = []
        for book in unified:
            key = (normalize_title(book.title), _author_sort_key(book.author))
            if key not in seen:
                seen.add(key)
                deduped.append(book)

        return deduped

    # ── EN источники ──────────────────────────

    async def _search_open_library(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await open_library.search(query, limit)
            return [
                UnifiedBook(
                    title=b.title, author=b.author, cover_url=b.cover_url,
                    source="Open Library", source_id=b.ia_id or "",
                    source_ids=b.ia_ids, year=b.year, languages=["en"],
                )
                for b in results if b.ia_id
            ]
        except Exception as e:
            logger.error(f"Open Library error: {e}")
            return []

    async def _search_gutenberg(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await gutenberg.search(query, limit)
            return [
                UnifiedBook(
                    title=b.title, author=_stringify_author(b.author), cover_url=b.cover_url,
                    source="Project Gutenberg",
                    source_id=b.pdf_url or b.epub_url or "",
                    languages=b.languages,
                )
                for b in results if (b.pdf_url or b.epub_url)
            ]
        except Exception as e:
            logger.error(f"Gutenberg error: {e}")
            return []

    async def _search_standard_ebooks(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await standard_ebooks.search(query, limit)
            return [
                UnifiedBook(
                    title=b.title, author=b.author, cover_url=b.cover_url,
                    source="Standard Ebooks", source_id=b.epub_url or "",
                    description=b.description, languages=["en"],
                )
                for b in results if b.epub_url
            ]
        except Exception as e:
            logger.error(f"Standard Ebooks error: {e}")
            return []

    # ── RU источники ──────────────────────────

    async def _search_archive_ru(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await archive_uz.search(query, language="rus", limit=limit + 20)
            logger.info(f"[archive_ru] raw_found={len(results)} for query={query!r}")

            # FIXED: раньше is_accessible() вызывался последовательно в for-цикле —
            # до 20+ HTTP-запросов к archive.org один за другим. Теперь параллельно.
            flags = await asyncio.gather(
                *[archive_uz.is_accessible(b.ia_id) for b in results],
                return_exceptions=True,
            )
            accessible = [
                UnifiedBook(
                    title=b.title, author=b.author, cover_url=b.cover_url,
                    source="Archive.org (RU)", source_id=b.ia_id,
                    languages=["ru"],
                )
                for b, ok in zip(results, flags) if ok is True
            ][:limit]

            logger.info(f"[archive_ru] accessible_found={len(accessible)} for query={query!r}")
            return accessible
        except Exception as e:
            logger.error(f"Archive RU error: {e}")
            return []

    async def _search_archive_uz(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await archive_uz.search(query, language="uzb", limit=limit + 10)

            # FIXED: то же самое — параллелим проверку доступности.
            flags = await asyncio.gather(
                *[archive_uz.is_accessible(b.ia_id) for b in results],
                return_exceptions=True,
            )
            accessible = [
                UnifiedBook(
                    title=b.title, author=b.author, cover_url=b.cover_url,
                    source="Archive.org (UZ)", source_id=b.ia_id,
                    languages=["uz"],
                )
                for b, ok in zip(results, flags) if ok is True
            ][:limit]

            return accessible
        except Exception as e:
            logger.error(f"Archive UZ error: {e}")
            return []

    async def _search_imwerden(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await imwerden.search(query, limit)
            return [
                UnifiedBook(
                    title=b.title, author=b.author, cover_url=b.cover_url,
                    source="ImWerden (Русская классика)",
                    source_id=b.pdf_url or "",
                    languages=["ru"],
                )
                for b in results if b.pdf_url
            ]
        except Exception as e:
            logger.error(f"ImWerden error: {e}")
            return []

    # ── Download ──────────────────────────────

    async def download(self, book: UnifiedBook) -> Optional[bytes]:
        if not book.source_id:
            return None
        try:
            if book.source == "Open Library":
                return await open_library.download_pdf(
                    ia_id=book.source_id,
                    ia_ids=book.source_ids or [book.source_id],
                )
            elif book.source == "Project Gutenberg":
                return await gutenberg.download_pdf(book.source_id)
            elif book.source == "Standard Ebooks":
                return await standard_ebooks.download_epub(book.source_id)
            elif book.source in ("Archive.org (RU)", "Archive.org (UZ)"):
                return await archive_uz.download_pdf(book.source_id)
            elif book.source == "ImWerden (Русская классика)":
                return await imwerden.download_pdf(book.source_id)
        except Exception as e:
            logger.error(f"Download error for {book.title}: {e}")
        return None

    async def get_cover_bytes(self, book: UnifiedBook) -> Optional[bytes]:
        if not book.cover_url:
            return None
        try:
            if book.source == "Open Library":
                return await open_library.get_cover_bytes(book.cover_url)
            elif book.source == "Project Gutenberg":
                return await gutenberg.get_cover_bytes(book.cover_url)
            elif book.source == "Standard Ebooks":
                return await standard_ebooks.get_cover_bytes(book.cover_url)
            elif book.source in ("Archive.org (RU)", "Archive.org (UZ)", "ImWerden (Русская классика)"):
                return await archive_uz.get_cover_bytes(book.cover_url)
        except Exception as e:
            logger.error(f"Cover error: {e}")
        return None

    def get_copyright_message(self, title: str, lang: str) -> str:
        lang = lang if lang in COPYRIGHT_MSG else "ru"
        return COPYRIGHT_MSG[lang].format(title=title)

    def get_download_failed_message(self, book: "UnifiedBook", lang: str) -> str:
        """
        FIXED: новый метод, который различает причину неудачного скачивания.
        Раньше всегда показывалось сообщение про копирайт, даже для источников
        типа Gutenberg/Standard Ebooks/Archive.org, где это просто технический сбой.
        """
        lang_key = lang if lang in COPYRIGHT_MSG else "ru"
        if book.source in _COPYRIGHT_CAPABLE_SOURCES:
            return COPYRIGHT_MSG[lang_key].format(title=book.title)
        return TECH_ERROR_MSG[lang_key].format(title=book.title)


aggregator = BookAggregator()  