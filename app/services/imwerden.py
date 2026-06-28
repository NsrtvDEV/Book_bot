"""
ImWerden — оцифрованная русская классика.
Сайт: https://imwerden.de
Большая коллекция русской поэзии и прозы в PDF.
"""
import logging
from dataclasses import dataclass
from typing import Optional
import aiohttp
from urllib.parse import quote

logger = logging.getLogger(__name__)

BASE_URL = "https://imwerden.de"
SEARCH_URL = "https://imwerden.de/search/?q={query}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KitobchiBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass
class ImWerdenBook:
    title: str
    author: Optional[str]
    pdf_url: Optional[str]
    cover_url: Optional[str] = None
    source: str = "ImWerden"


class ImWerdenService:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers=HEADERS,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, query: str, limit: int = 3) -> list[ImWerdenBook]:
        """Поиск через Archive.org фильтруя по imwerden collection."""
        session = await self._get_session()

        # ImWerden загружает свои книги на Archive.org
        params = {
            "q": f'title:({query}) AND collection:imwerden AND mediatype:texts',
            "fl[]": "identifier,title,creator",
            "rows": limit,
            "page": 1,
            "output": "json",
        }
        try:
            async with session.get(
                "https://archive.org/advancedsearch.php", params=params
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception as e:
            logger.error(f"ImWerden search error: {e}")
            return []

        results = []
        for doc in data.get("response", {}).get("docs", []):
            ia_id = doc.get("identifier", "")
            if not ia_id:
                continue
            results.append(ImWerdenBook(
                title=doc.get("title", "Unknown"),
                author=doc.get("creator"),
                pdf_url=ia_id,  # используем ia_id для скачивания
                cover_url=f"https://archive.org/services/img/{ia_id}",
                source="ImWerden (Русская классика)",
            ))
        return results

    async def download_pdf(self, ia_id: str) -> Optional[bytes]:
        """Скачивает PDF через Archive.org."""
        from app.services.archive_uz import archive_uz
        return await archive_uz.download_pdf(ia_id)

    async def get_cover_bytes(self, cover_url: str) -> Optional[bytes]:
        from app.services.archive_uz import archive_uz
        return await archive_uz.get_cover_bytes(cover_url)


imwerden = ImWerdenService()