"""Lightweight static-page fetching via Scrapling - no browser involved.

Use this for quick reads of static pages/APIs/articles. It doesn't touch the
shared agent-Chrome browser (no CDP roundtrip, doesn't disturb whatever tab
the user is looking at), and it can't run JavaScript - for pages that need
that, use the browser tools (goto_url/read_page) instead.
"""

import asyncio

from scrapling.fetchers import Fetcher

MAX_CHARS = 8000


def _fetch(url: str) -> str:
    page = Fetcher.get(url, stealthy_headers=True)
    title = page.css("title::text").get(default="").strip()
    text = page.get_all_text(ignore_tags=("script", "style", "noscript")).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n...[truncated]"
    return f"Title: {title}\nURL: {url}\nStatus: {page.status}\n\n{text}"


async def fetch_page(url: str) -> str:
    """Fetch a static page and return its title + visible text. Runs in a thread (blocking call)."""
    try:
        return await asyncio.to_thread(_fetch, url)
    except Exception as e:
        return f"Failed to fetch {url}: {e}"
