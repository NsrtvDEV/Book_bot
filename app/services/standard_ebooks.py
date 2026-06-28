"""
Standard Ebooks — высококачественные бесплатные книги.
Красивое форматирование, без рекламы.
Официальный каталог: https://standardebooks.org/feeds
"""
import logging
from dataclasses import dataclass
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

CATALOG_URL = "https://standardebooks.org/feeds/opds"
SEARCH_URL = "https://standardebooks.org/ebooks?query={query}&per-page=6"


@dataclass
class StandardBook:
    title: str
    author: Optional[str]
    cover_url: Optional[str]
    epub_url: Optional[str]
    description: Optional[str]
    source: str = "Standard Ebooks"


class StandardEbooksService:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "KitobchiBot/1.0 (book search bot)"},
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, query: str, limit: int = 3) -> list[StandardBook]:
        """Поиск через OPDS каталог Standard Ebooks."""
        session = await self._get_session()
        url = f"https://standardebooks.org/feeds/opds/all?query={query}"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception as e:
            logger.error(f"Standard Ebooks search error: {e}")
            return []

        return self._parse_opds(text, limit)

    def _parse_opds(self, xml_text: str, limit: int) -> list[StandardBook]:
        """Парсит OPDS XML ответ."""
        import xml.etree.ElementTree as ET

        results = []
        try:
            root = ET.fromstring(xml_text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "dc": "http://purl.org/dc/terms/",
            }
            entries = root.findall("atom:entry", ns)

            for entry in entries[:limit]:
                title = entry.findtext("atom:title", default="Unknown", namespaces=ns)
                author_el = entry.find("atom:author/atom:name", ns)
                author = author_el.text if author_el is not None else None
                summary = entry.findtext("atom:summary", default=None, namespaces=ns)

                cover_url = None
                epub_url = None
                for link in entry.findall("atom:link", ns):
                    rel = link.get("rel", "")
                    href = link.get("href", "")
                    mime = link.get("type", "")
                    if "cover" in rel or "thumbnail" in rel:
                        cover_url = href
                    if "epub" in mime:
                        epub_url = href

                if title and title != "Unknown":
                    results.append(StandardBook(
                        title=title,
                        author=author,
                        cover_url=cover_url,
                        epub_url=epub_url,
                        description=summary,
                        source="Standard Ebooks",
                    ))
        except Exception as e:
            logger.error(f"Standard Ebooks parse error: {e}")

        return results

    async def download_epub(self, epub_url: str) -> Optional[bytes]:
        session = await self._get_session()
        try:
            async with session.get(epub_url) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception as e:
            logger.error(f"Standard Ebooks epub download error: {e}")
            return None

    async def get_cover_bytes(self, cover_url: str) -> Optional[bytes]:
        session = await self._get_session()
        try:
            async with session.get(cover_url) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception as e:
            return None


standard_ebooks = StandardEbooksService() 
