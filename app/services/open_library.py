"""Open Library API — поиск и скачивание PDF."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

SEARCH_URL = "https://openlibrary.org/search.json"
COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BookBot/1.0)"}
MAX_PDF_SIZE = 49 * 1024 * 1024  # 49 MB — чуть меньше лимита Telegram


@dataclass
class BookResult:
    key: str
    title: str
    author: Optional[str]
    cover_url: Optional[str]
    ia_id: Optional[str]
    ia_ids: list[str] = field(default_factory=list)  # все доступные издания
    year: Optional[int] = None
    source: str = "Open Library"


class OpenLibraryService:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120, connect=10),
                headers=HEADERS,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def search(self, query: str, limit: int = 3) -> list[BookResult]:
        session = await self._get_session()
        params = {
            "q": query,
            "limit": limit,
            "fields": "key,title,author_name,cover_i,ia,first_publish_year",
            "has_fulltext": "true",
        }
        try:
            async with session.get(SEARCH_URL, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception as e:
            logger.error(f"Open Library search error: {e}")
            return []

        results = []
        for doc in data.get("docs", []):
            ia_list = doc.get("ia", [])
            cover_id = doc.get("cover_i")
            results.append(BookResult(
                key=doc.get("key", ""),
                title=doc.get("title", "Unknown"),
                author=", ".join(doc.get("author_name", [])) or None,
                cover_url=COVER_URL.format(cover_id=cover_id) if cover_id else None,
                ia_id=ia_list[0] if ia_list else None,
                ia_ids=ia_list,  # сохраняем ВСЕ издания
                year=doc.get("first_publish_year"),
            ))
        return results

    async def _get_best_pdf_from_ia(self, ia_id: str) -> Optional[tuple[str, int]]:
        """
        Возвращает (url, size_bytes) лучшего PDF для данного ia_id.
        None если книга недоступна или PDF нет.
        """
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
            logger.error(f"Archive.org metadata error for {ia_id}: {e}")
            return None

        meta = data.get("metadata", {})
        if meta.get("access-restricted-item") == "true":
            logger.info(f"{ia_id}: access restricted")
            return None

        files = data.get("files", [])
        pdf_files = [
            f for f in files
            if f.get("name", "").endswith(".pdf")
            and "encrypted" not in f.get("name", "")
        ]
        if not pdf_files:
            return None

        # Приоритет: Text PDF, потом меньший размер
        def sort_key(f):
            is_text_pdf = f.get("format") == "Text PDF"
            size = int(f.get("size", 999_999_999))
            return (not is_text_pdf, size)

        pdf_files.sort(key=sort_key)
        best = pdf_files[0]
        size = int(best.get("size", 0))
        url = f"https://archive.org/download/{ia_id}/{best['name']}"
        return url, size

    async def get_pdf_url(self, ia_id: str) -> Optional[str]:
        """Возвращает URL PDF для данного ia_id (без проверки размера)."""
        result = await self._get_best_pdf_from_ia(ia_id)
        return result[0] if result else None

    async def find_downloadable_pdf(self, ia_ids: list[str]) -> Optional[str]:
        """
        Перебирает все издания книги и возвращает URL первого PDF < 49MB.
        Если все большие — возвращает URL наименьшего.

        FIXED: раньше издания перебирались по одному в последовательном
        for-цикле (каждое — отдельный HTTP-запрос к archive.org metadata).
        Для книг с несколькими изданиями это заметно тормозило скачивание.
        Теперь все метаданные запрашиваются параллельно, а выбор лучшего
        издания делается после получения всех результатов.
        """
        if not ia_ids:
            return None

        results = await asyncio.gather(
            *[self._get_best_pdf_from_ia(ia_id) for ia_id in ia_ids],
            return_exceptions=True,
        )

        best_url = None
        best_size = None

        for ia_id, result in zip(ia_ids, results):
            if isinstance(result, Exception) or not result:
                if isinstance(result, Exception):
                    logger.error(f"Archive.org metadata error for {ia_id}: {result}")
                continue

            url, size = result
            logger.info(f"{ia_id}: PDF size = {size / 1024 / 1024:.1f} MB")

            if size <= MAX_PDF_SIZE:
                logger.info(f"{ia_id}: fits in Telegram limit, using this one")
                return url

            # Запоминаем наименьший из больших
            if best_size is None or size < best_size:
                best_url = url
                best_size = size

        if best_url:
            logger.warning(f"All PDFs are >49MB, using smallest: {best_size / 1024 / 1024:.1f} MB")
        return best_url

    async def _download_url(self, pdf_url: str, ia_id: str = "?") -> Optional[bytes]:
        """Скачивает PDF по URL, проверяет что это реальный PDF и не превышает лимит."""
        session = await self._get_session()
        try:
            async with session.get(pdf_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    logger.warning(f"PDF download got status {resp.status} for {pdf_url}")
                    return None

                content_type = resp.headers.get("Content-Type", "")
                if "html" in content_type:
                    logger.warning(f"{ia_id}: got HTML instead of PDF (login wall?)")
                    return None

                chunks = []
                total = 0
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    total += len(chunk)
                    if total > MAX_PDF_SIZE:
                        logger.warning(f"{ia_id}: PDF too large (>{MAX_PDF_SIZE // 1024 // 1024}MB)")
                        return None
                    chunks.append(chunk)

                data = b"".join(chunks)
                if not data.startswith(b"%PDF"):
                    logger.warning(f"{ia_id}: not a PDF (starts with {data[:8].hex()})")
                    return None

                logger.info(f"{ia_id}: downloaded {total / 1024 / 1024:.1f} MB")
                return data

        except aiohttp.ClientError as e:
            logger.error(f"PDF download error for {ia_id}: {e}")
            return None

    async def download_pdf(self, ia_id: str, ia_ids: list[str] = None) -> Optional[bytes]:
        """
        Скачивает PDF. Если текущий ia_id слишком большой —
        перебирает все ia_ids чтобы найти меньший вариант.
        """
        all_ids = ia_ids or [ia_id]

        # Ищем подходящий PDF среди всех изданий
        pdf_url = await self.find_downloadable_pdf(all_ids)
        if not pdf_url:
            logger.warning(f"No downloadable PDF found for ia_ids={all_ids}")
            return None

        return await self._download_url(pdf_url, ia_id)

    async def get_cover_bytes(self, cover_url: str) -> Optional[bytes]:
        session = await self._get_session()
        try:
            async with session.get(cover_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception as e:
            logger.error(f"Cover download error: {e}")
            return None


open_library = OpenLibraryService() 