"""
Archive.org — узбекская и русская коллекции книг.
Коллекции:
  https://archive.org/details/booksbylanguage_uzbek
  https://archive.org/details/booksbylanguage_russian
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

SEARCH_URL = "https://archive.org/advancedsearch.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KitobchiBot/1.0)"}

COLLECTION_MAP = {
    "uzb": "booksbylanguage_uzbek",
    "rus": "booksbylanguage_russian",
}


@dataclass
class ArchiveBook:
    ia_id: str
    title: str
    author: Optional[str]
    cover_url: Optional[str]
    language: str
    source: str = "Archive.org"


class ArchiveUzService:
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

    async def search(self, query: str, language: str = "uzb", limit: int = 3) -> list[ArchiveBook]:
        """
        Поиск книг на Archive.org.
        language: 'uzb' для узбекского, 'rus' для русского.
        Ищем по коллекции (а не по полю language, оно заполнено непоследовательно),
        и по title ИЛИ creator (имя автора тоже должно находиться).
        """
        session = await self._get_session()

        collection = COLLECTION_MAP.get(language)
        if collection:
            q = f'collection:{collection} AND (title:({query}) OR creator:({query})) AND mediatype:texts'
        else:
            q = f'(title:({query}) OR creator:({query})) AND language:{language} AND mediatype:texts'

        params = {
            "q": q,
            "fl[]": "identifier,title,creator,language",
            "rows": limit,
            "page": 1,
            "output": "json",
        }
        try:
            async with session.get(SEARCH_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Archive.org search status={resp.status} q={q!r}")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.error(f"Archive.org search error ({language}): {e}")
            return []

        docs = data.get("response", {}).get("docs", [])
        logger.info(f"[archive_uz] query={query!r} lang={language} found={len(docs)}")

        results = []
        for doc in docs:
            ia_id = doc.get("identifier", "")
            results.append(ArchiveBook(
                ia_id=ia_id,
                title=doc.get("title", "Unknown"),
                author=doc.get("creator"),
                cover_url=f"https://archive.org/services/img/{ia_id}" if ia_id else None,
                language=language,
            ))
        return results

    async def is_accessible(self, ia_id: str) -> bool:
        """Проверяет что книга не закрыта авторскими правами."""
        session = await self._get_session()
        try:
            async with session.get(
                f"https://archive.org/metadata/{ia_id}",
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
        except Exception:
            return False

        meta = data.get("metadata", {})
        if meta.get("access-restricted-item") == "true":
            return False

        files = data.get("files", [])
        has_pdf = any(
            f.get("name", "").endswith(".pdf") and "encrypted" not in f.get("name", "")
            for f in files
        )
        return has_pdf

    async def get_pdf_url(self, ia_id: str) -> Optional[str]:
        session = await self._get_session()
        try:
            async with session.get(
                f"https://archive.org/metadata/{ia_id}",
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception as e:
            logger.error(f"Archive metadata error: {e}")
            return None

        if data.get("metadata", {}).get("access-restricted-item") == "true":
            return None

        for f in data.get("files", []):
            name = f.get("name", "")
            fmt = f.get("format", "")
            if fmt == "Text PDF" and "encrypted" not in name:
                return f"https://archive.org/download/{ia_id}/{name}"

        for f in data.get("files", []):
            name = f.get("name", "")
            if name.endswith(".pdf") and "encrypted" not in name:
                return f"https://archive.org/download/{ia_id}/{name}"

        return None

    async def download_pdf(self, ia_id: str) -> Optional[bytes]:
        pdf_url = await self.get_pdf_url(ia_id)
        if not pdf_url:
            return None
        session = await self._get_session()
        try:
            async with session.get(pdf_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                content_type = resp.headers.get("Content-Type", "")
                if "html" in content_type:
                    return None
                data = await resp.read()
                if not data.startswith(b"%PDF"):
                    return None
                logger.info(f"Archive.org downloaded: {ia_id} ({len(data) // 1024} KB)")
                return data
        except Exception as e:
            logger.error(f"Archive.org download error: {e}")
            return None

    async def get_cover_bytes(self, cover_url: str) -> Optional[bytes]:
        session = await self._get_session()
        try:
            async with session.get(cover_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception:
            return None


archive_uz = ArchiveUzService() 