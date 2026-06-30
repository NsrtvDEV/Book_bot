"""
ImWerden — оцифрованная русская классика.
Сайт: https://imwerden.de
Большая коллекция русской поэзии и прозы в PDF.
Загружена на Archive.org под отдельной коллекцией "imwerden".
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
import aiohttp

from app.services.archive_uz import archive_uz, normalize_uzbek_query, fuzzify

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KitobchiBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}

SEARCH_URL = "https://archive.org/advancedsearch.php"


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

    async def _raw_search(self, q: str, limit: int) -> list[dict]:
        session = await self._get_session()
        params = {
            "q": q,
            "fl[]": "identifier,title,creator",
            "rows": limit,
            "page": 1,
            "output": "json",
        }
        try:
            async with session.get(SEARCH_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"ImWerden search status={resp.status} q={q!r}")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.error(f"ImWerden search error: {e}")
            return []
        return data.get("response", {}).get("docs", [])

    async def search(self, query: str, limit: int = 3) -> list[ImWerdenBook]:
        """
        Поиск в коллекции imwerden на Archive.org.
        Пробуем точный запрос -> без апострофов -> fuzzy (опечатки),
        и фильтруем по реальной доступности файла (как в archive_uz).
        """
        normalized = normalize_uzbek_query(query)
        fuzzy = fuzzify(normalized if normalized != query else query)

        queries_to_try = [query]
        if normalized != query:
            queries_to_try.append(normalized)
        if fuzzy not in queries_to_try:
            queries_to_try.append(fuzzy)

        seen_ids = set()
        candidates: list[dict] = []

        for q_text in queries_to_try:
            q = f'collection:imwerden AND (title:({q_text}) OR creator:({q_text})) AND mediatype:texts'
            docs = await self._raw_search(q, limit + 10)
            logger.info(f"[imwerden] query={q_text!r} found={len(docs)}")

            for doc in docs:
                ia_id = doc.get("identifier", "")
                if not ia_id or ia_id in seen_ids:
                    continue
                seen_ids.add(ia_id)
                candidates.append(doc)

            if len(candidates) >= limit + 10:
                break

        # FIXED: раньше is_accessible() вызывался последовательно в for-цикле для
        # каждого кандидата — до 10+ HTTP-запросов к archive.org один за другим.
        # Теперь проверяем доступность всех кандидатов параллельно.
        flags = await asyncio.gather(
            *[archive_uz.is_accessible(doc.get("identifier", "")) for doc in candidates],
            return_exceptions=True,
        )

        results: list[ImWerdenBook] = []
        for doc, ok in zip(candidates, flags):
            if ok is not True:
                continue
            ia_id = doc.get("identifier", "")
            results.append(ImWerdenBook(
                title=doc.get("title", "Unknown"),
                author=doc.get("creator"),
                pdf_url=ia_id,
                cover_url=f"https://archive.org/services/img/{ia_id}",
                source="ImWerden (Русская классика)",
            ))
            if len(results) >= limit:
                break

        logger.info(f"[imwerden] accessible_found={len(results)} for query={query!r}")
        return results

    async def download_pdf(self, ia_id: str) -> Optional[bytes]:
        """Скачивает PDF через Archive.org."""
        return await archive_uz.download_pdf(ia_id)

    async def get_cover_bytes(self, cover_url: str) -> Optional[bytes]:
        return await archive_uz.get_cover_bytes(cover_url)


imwerden = ImWerdenService() 