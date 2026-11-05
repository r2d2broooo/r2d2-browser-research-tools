"""Playwright CDP client for the dedicated "agent Chrome" instance.

The user runs a separate Chrome profile (~/.config/chrome-agent) with
--remote-debugging-port=9222, pre-logged-in to the accounts the AI models
are allowed to use. This module gives selector-based read/navigate/click
access to that browser - much more reliable than pixel-coordinate desktop
automation.
"""

import asyncio
import subprocess
import time
import urllib.request

from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"
MAX_TEXT_CHARS = 4000


def _cdp_alive(timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(CDP_URL + "/json/version", timeout=timeout).read()
        return True
    except Exception:
        return False


def _ensure_browser(wait: float = 30.0) -> None:
    """Start the agent Chrome on demand if it isn't up.

    agent-browser.service is Restart=on-failure (changed 2026-08-25), so a
    window the user closed by hand stays closed - Restart=always used to
    reopen it ~5s later, which made the browser impossible to dismiss. Nothing
    else would bring it back, so the first call that needs it starts it.
    """
    if _cdp_alive():
        return
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "agent-browser.service"],
            check=False,
            timeout=30,
        )
    except Exception:
        return
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if _cdp_alive():
            return
        time.sleep(1)


def _with_page(fn):
    """Connect over CDP, get the active page, run fn(page).

    Deliberately does NOT call browser.close() - for CDP connections that
    sends a Browser.close command that terminates the whole Chrome process,
    not just this connection. Exiting the `with sync_playwright()` block
    cleans up the local driver only.
    """
    _ensure_browser()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        contexts = browser.contexts
        all_pages = []
        for ctx in contexts:
            all_pages.extend(ctx.pages)

        if all_pages:
            page = all_pages[-1]
        else:
            ctx = contexts[0] if contexts else browser.new_context()
            page = ctx.new_page()
        return fn(page)


def _wait_for_settled(page) -> None:
    """Best-effort wait for the page to finish loading before reading/screenshotting it.
    Tolerates pages that never go fully idle (e.g. websockets/live charts)."""
    try:
        page.wait_for_load_state("load", timeout=10000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(1000)


def _screenshot_sync() -> bytes:
    def run(page):
        _wait_for_settled(page)
        return page.screenshot(type="png")
    return _with_page(run)


def _screenshot_fast_sync() -> bytes:
    """Screenshot without waiting for the page to settle - for rapid-fire
    recording of a live session (the page is expected to be mid-interaction)."""
    return _with_page(lambda page: page.screenshot(type="png"))


def _goto_sync(url: str) -> dict:
    def run(page):
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_settled(page)
        return {"title": page.title(), "url": page.url}
    return _with_page(run)


def _screenshot_url_sync(url: str, wait: float = 6.0) -> bytes:
    """Open URL in a DEDICATED new tab, screenshot it, close the tab.

    Deliberately not `goto` on the active page: the operator's TradingView tab holds their chart
    layout and Pine editor, and navigating it away both destroys their working state and detaches
    the SPA's frames mid-navigation ("Frame has been detached").
    """
    _ensure_browser()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(int(max(wait, 0) * 1000))
            try:
                return page.screenshot(timeout=30000, animations="disabled")
            except Exception:
                # canvas-heavy pages can stall Playwright's capture; fall back to raw CDP
                cdp = ctx.new_cdp_session(page)
                import base64
                shot = cdp.send("Page.captureScreenshot", {"format": "png"})
                return base64.b64decode(shot["data"])
        finally:
            try:
                page.close()
            except Exception:
                pass


def _read_page_sync() -> dict:
    def run(page):
        _wait_for_settled(page)
        text = page.inner_text("body")
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "..."
        return {"title": page.title(), "url": page.url, "text": text}
    return _with_page(run)


def _search_sync(query: str) -> dict:
    import urllib.parse

    def run(page):
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _wait_for_settled(page)
        try:
            text = page.inner_text("#links")
        except Exception:
            text = page.inner_text("body")
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "..."
        return {"title": page.title(), "url": page.url, "text": text}
    return _with_page(run)


def _click_sync(selector: str) -> None:
    _with_page(lambda page: page.click(selector, timeout=10000))


def _fill_sync(selector: str, text: str) -> None:
    _with_page(lambda page: page.fill(selector, text, timeout=10000))


def _press_key_sync(key: str) -> None:
    _with_page(lambda page: page.keyboard.press(key))


def _record_frames_sync(seconds: float, interval: float, sdir: str) -> list[str]:
    """Capture a burst of screenshots over a single CDP connection.

    Uses a raw CDP `Page.captureScreenshot` call instead of Playwright's
    page.screenshot()/title() - those wait on the page's JS main thread,
    which can hang indefinitely on a busy live page (e.g. a TradingView
    chart that's constantly rendering). The raw CDP screenshot is served
    by the browser/compositor and returns near-instantly regardless."""
    import base64
    import os
    import time

    frames: list[str] = []
    _ensure_browser()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        all_pages = []
        for ctx in browser.contexts:
            all_pages.extend(ctx.pages)
        if not all_pages:
            return frames
        page = all_pages[-1]
        cdp = page.context.new_cdp_session(page)

        deadline = time.monotonic() + seconds
        i = 0
        while time.monotonic() < deadline:
            try:
                res = cdp.send("Page.captureScreenshot", {"format": "png"})
                png = base64.b64decode(res["data"])
                path = os.path.join(sdir, f"frame_{i:03d}.png")
                with open(path, "wb") as f:
                    f.write(png)
                frames.append(path)
                i += 1
            except Exception:
                pass
            time.sleep(interval)
    return frames


def _list_tabs_sync() -> list[dict]:
    _ensure_browser()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        tabs = []
        for ctx in browser.contexts:
            for page in ctx.pages:
                tabs.append({"title": page.title(), "url": page.url})
        return tabs


async def screenshot() -> bytes:
    return await asyncio.to_thread(_screenshot_sync)


async def screenshot_fast() -> bytes:
    return await asyncio.to_thread(_screenshot_fast_sync)


async def record_frames(seconds: float, interval: float, sdir: str) -> list[str]:
    """Capture a burst of screenshots into sdir, one CDP connection for the whole burst."""
    return await asyncio.to_thread(_record_frames_sync, seconds, interval, sdir)


async def goto(url: str) -> dict:
    """Navigate the active tab to url. SAFE."""
    return await asyncio.to_thread(_goto_sync, url)


async def screenshot_url(url: str, wait: float = 6.0) -> bytes:
    return await asyncio.to_thread(_screenshot_url_sync, url, wait)


async def read_page() -> dict:
    """Return {title, url, text} for the active tab. SAFE."""
    return await asyncio.to_thread(_read_page_sync)


async def search(query: str) -> dict:
    """Run a web search (DuckDuckGo HTML results) and return {title, url, text}. SAFE."""
    return await asyncio.to_thread(_search_sync, query)


async def click(selector: str) -> None:
    """Click an element by CSS selector. ACTION - requires confirmation."""
    await asyncio.to_thread(_click_sync, selector)


async def fill(selector: str, text: str) -> None:
    """Fill a form field by CSS selector. ACTION - requires confirmation."""
    await asyncio.to_thread(_fill_sync, selector, text)


async def press_key(key: str) -> None:
    """Press a key (e.g. 'Enter', 'PageDown'). ACTION - requires confirmation."""
    await asyncio.to_thread(_press_key_sync, key)


async def list_tabs() -> list[dict]:
    return await asyncio.to_thread(_list_tabs_sync)
