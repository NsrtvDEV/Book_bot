"""
Агрегатор всех источников книг.
Ищет параллельно во всех источниках и возвращает единый список.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.services.open_library import open_library, BookResult
from app.services.gutenberg import gutenberg, GutenbergBook
from app.services.standard_ebooks import standard_ebooks, StandardBook

logger = logging.getLogger(__name__)


@dataclass
class UnifiedBook:
    """Единый формат книги из любого источника."""
    title: str
    author: Optional[str]
    cover_url: Optional[str]
    source: str                 # "Open Library", "Project Gutenberg", "Standard Ebooks"
    source_id: str              # ia_id, pdf_url, epub_url — для скачивания
    source_ids: list[str] = field(default_factory=list)  # все ia_id (для Open Library)
    year: Optional[int] = None
    description: Optional[str] = None
    languages: list[str] = field(default_factory=list)


class BookAggregator:

    async def search_all(self, query: str, limit_per_source: int = 3) -> list[UnifiedBook]:
        """Параллельный поиск во всех источниках."""
        tasks = [
            self._search_open_library(query, limit_per_source),
            self._search_gutenberg(query, limit_per_source),
            self._search_standard_ebooks(query, limit_per_source),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        unified = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Source error: {result}")
                continue
            unified.extend(result)

        # Убираем дубликаты по названию
        seen = set()
        deduped = []
        for book in unified:
            key = book.title.lower()[:30]
            if key not in seen:
                seen.add(key)
                deduped.append(book)

        return deduped

    async def _search_open_library(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await open_library.search(query, limit)
            return [
                UnifiedBook(
                    title=b.title,
                    author=b.author,
                    cover_url=b.cover_url,
                    source="Open Library",
                    source_id=b.ia_id or "",
                    source_ids=b.ia_ids,   # все издания для поиска меньшего PDF
                    year=b.year,
                    languages=["en"],
                )
                for b in results if b.ia_id
            ]
        except Exception as e:
            logger.error(f"Open Library aggregator error: {e}")
            return []

    async def _search_gutenberg(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await gutenberg.search(query, limit)
            return [
                UnifiedBook(
                    title=b.title,
                    author=b.author,
                    cover_url=b.cover_url,
                    source="Project Gutenberg",
                    source_id=b.pdf_url or b.epub_url or "",
                    languages=b.languages,
                )
                for b in results if (b.pdf_url or b.epub_url)
            ]
        except Exception as e:
            logger.error(f"Gutenberg aggregator error: {e}")
            return []

    async def _search_standard_ebooks(self, query: str, limit: int) -> list[UnifiedBook]:
        try:
            results = await standard_ebooks.search(query, limit)
            return [
                UnifiedBook(
                    title=b.title,
                    author=b.author,
                    cover_url=b.cover_url,
                    source="Standard Ebooks",
                    source_id=b.epub_url or "",
                    description=b.description,
                    languages=["en"],
                )
                for b in results if b.epub_url
            ]
        except Exception as e:
            logger.error(f"Standard Ebooks aggregator error: {e}")
            return []

    async def download(self, book: UnifiedBook) -> Optional[bytes]:
        """Скачивает файл книги в зависимости от источника."""
        if not book.source_id:
            return None

        if book.source == "Open Library":
            # Передаём все ia_ids чтобы найти издание поменьше
            return await open_library.download_pdf(
                ia_id=book.source_id,
                ia_ids=book.source_ids or [book.source_id],
            )

        elif book.source == "Project Gutenberg":
            return await gutenberg.download_pdf(book.source_id)

        elif book.source == "Standard Ebooks":
            return await standard_ebooks.download_epub(book.source_id)

        return None

    async def get_cover_bytes(self, book: UnifiedBook) -> Optional[bytes]:
        if not book.cover_url:
            return None
        if book.source == "Open Library":
            return await open_library.get_cover_bytes(book.cover_url)
        elif book.source == "Project Gutenberg":
            return await gutenberg.get_cover_bytes(book.cover_url)
        elif book.source == "Standard Ebooks":
            return await standard_ebooks.get_cover_bytes(book.cover_url)
        return None


aggregator = BookAggregator()