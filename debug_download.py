"""
Запусти этот скрипт чтобы проверить скачивание:
uv run python debug_download.py "название книги"
"""
import asyncio
import sys
import aiohttp

HEADERS = {
    "User-Agent": "BookBot/1.0 (educational project; contact: you@example.com)"
}


async def check_url(session: aiohttp.ClientSession, url: str, label: str = ""):
    """Follow redirects and report final status + first few bytes."""
    try:
        # Use GET with allow_redirects=True to actually follow the chain
        async with session.get(
            url, headers=HEADERS, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            final_url = str(resp.url)
            status = resp.status
            content_type = resp.headers.get("Content-Type", "?")
            content_length = resp.headers.get("Content-Length", "?")

            # Read just the first 8 bytes to confirm it's a real PDF
            chunk = await resp.content.read(8)
            is_pdf = chunk.startswith(b"%PDF")

            redirected = final_url != url

            print(f"      {'[' + label + '] ' if label else ''}Status: {status}")
            if redirected:
                print(f"      Redirected → {final_url[:80]}...")
            print(f"      Content-Type: {content_type}")
            print(f"      Content-Length: {content_length} bytes")
            print(f"      Starts with %PDF: {'✅ YES' if is_pdf else '❌ NO (first bytes: ' + chunk.hex() + ')'}")
            return status == 200 and is_pdf

    except asyncio.TimeoutError:
        print(f"      ❌ Timeout after 15s")
        return False
    except Exception as e:
        print(f"      ❌ Error: {e}")
        return False


async def test_open_library(query: str):
    print(f"\n=== Open Library: '{query}' ===")
    async with aiohttp.ClientSession() as session:
        params = {
            "q": query,
            "limit": 3,
            "fields": "key,title,author_name,cover_i,ia",
            "has_fulltext": "true",
        }
        async with session.get(
            "https://openlibrary.org/search.json", params=params, headers=HEADERS
        ) as resp:
            data = await resp.json()

        for doc in data.get("docs", []):
            title = doc.get("title")
            ia_list = doc.get("ia", [])
            ia_id = ia_list[0] if ia_list else None
            print(f"\n  📖 {title}")
            print(f"     ia_id: {ia_id}")

            if not ia_id:
                print("     ❌ No ia_id — skipping")
                continue

            # Check lending status via metadata
            async with session.get(
                f"https://archive.org/metadata/{ia_id}", headers=HEADERS
            ) as meta_resp:
                meta = await meta_resp.json()

            access = meta.get("metadata", {}).get("access-restricted-item", "false")
            lending = meta.get("metadata", {}).get("loans__status__status", "")
            print(f"     Access restricted: {access}")
            print(f"     Lending status: '{lending}' (empty = freely downloadable)")

            files = meta.get("files", [])
            pdf_files = [f for f in files if f.get("name", "").endswith(".pdf")]
            # Prefer non-encrypted Text PDFs
            pdf_files.sort(key=lambda f: (
                "encrypted" in f.get("name", ""),   # encrypted last
                f.get("format", "") != "Text PDF",   # Text PDF first
            ))

            print(f"     PDF files found: {len(pdf_files)}")
            for f in pdf_files[:2]:
                name = f.get("name")
                fmt = f.get("format")
                url = f"https://archive.org/download/{ia_id}/{name}"
                print(f"\n     → {name} ({fmt})")
                downloadable = await check_url(session, url)
                if downloadable:
                    print(f"     ✅ DOWNLOADABLE")
                else:
                    print(f"     ⚠️  Not freely downloadable (likely needs borrowing)")


async def test_gutenberg(query: str):
    print(f"\n=== Project Gutenberg: '{query}' ===")
    async with aiohttp.ClientSession() as session:
        params = {"search": query, "mime_type": "application/pdf"}
        async with session.get(
            "https://gutendex.com/books", params=params, headers=HEADERS
        ) as resp:
            data = await resp.json()

        results = data.get("results", [])
        if not results:
            print("  No results found.")
            return

        for book in results[:3]:
            title = book.get("title")
            formats = book.get("formats", {})
            pdf_url = formats.get("application/pdf")
            print(f"\n  📖 {title}")
            print(f"     PDF URL: {pdf_url}")

            if pdf_url:
                downloadable = await check_url(session, pdf_url)
                if downloadable:
                    print(f"     ✅ DOWNLOADABLE")
            else:
                print("     ❌ No PDF format available")
                # Show what formats ARE available
                print(f"     Available formats: {list(formats.keys())[:5]}")


async def main():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "war and peace"
    await test_open_library(query)
    await test_gutenberg(query)


asyncio.run(main()) 