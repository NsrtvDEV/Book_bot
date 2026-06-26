"""
Project Gutenberg через Gutendex API.
Бесплатно, без ключа: https://gutendex.com
70,000+ книг публичного домена.
"""
import logging
from dataclasses import dataclass
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

GUTENDEX_URL = "https://gutendex.com/books"


@dataclass
class GutenbergBook:
    gutenberg_id: int
    title: str
    author: Optional[str]
    cover_url: Optional[str]
    pdf_url: Optional[str]
    epub_url: Optional[str]
    languages: list[str]
    source: str = "Project Gutenberg"


class GutenbergService:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, query: str, limit: int = 3) -> list[GutenbergBook]:
        """Поиск книг через Gutendex API."""
        session = await self._get_session()
        params = {"search": query, "mime_type": "application/pdf"}

        try:
            async with session.get(GUTENDEX_URL, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception as e:
            logger.error(f"Gutendex search error: {e}")
            return []

        results = []
        for book in data.get("results", [])[:limit]:
            formats = book.get("formats", {})

            # Ищем PDF
            pdf_url = formats.get("application/pdf")

            # Обложка
            cover_url = formats.get("image/jpeg")

            # Авторы
            authors = book.get("authors", [])
            author = authors[0].get("name") if authors else None
            if author:
                # Gutenberg хранит как "Austen, Jane" — переворачиваем
                parts = author.split(", ", 1)
                author = f"{parts[1]} {parts[0]}" if len(parts) == 2 else author

            results.append(GutenbergBook(
                gutenberg_id=book.get("id"),
                title=book.get("title", "Unknown"),
                author=author,
                cover_url=cover_url,
                pdf_url=pdf_url,
                epub_url=formats.get("application/epub+zip"),
                languages=book.get("languages", []),
                source="Project Gutenberg",
            ))

        return results

    async def download_pdf(self, pdf_url: str) -> Optional[bytes]:
        """Скачивает PDF по прямой ссылке."""
        session = await self._get_session()
        try:
            async with session.get(pdf_url) as resp:
                if resp.status != 200:
                    return None
                content = await resp.read()
                logger.info(f"Gutenberg PDF downloaded: {len(content) // 1024} KB")
                return content
        except Exception as e:
            logger.error(f"Gutenberg PDF download error: {e}")
            return None

    async def get_cover_bytes(self, cover_url: str) -> Optional[bytes]:
        session = await self._get_session()
        try:
            async with session.get(cover_url) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception as e:
            logger.error(f"Gutenberg cover error: {e}")
            return None


gutenberg = GutenbergService()