"""Clean main-content extraction — denoise a captured page before an LLM reads it.

Captured pages (CDP innerText, or raw HTML) carry nav bars, cookie banners, footers,
related-article rails — noise that wastes tokens and seeds hallucinations. This pulls the
main article/body text out.

Prefers trafilatura (best HTML→text). Falls back to a bs4 strip, then a line heuristic on
plain text. Never raises — worst case it returns the input lightly cleaned.
"""
from __future__ import annotations

import re

_BOILER = {
    "sign in", "log in", "subscribe", "subscribe now", "advertisement", "menu",
    "skip to content", "skip to main content", "share", "newsletter", "cookie policy",
    "accept all cookies", "accept cookies", "manage cookies", "back to top",
    "all rights reserved", "terms of service", "privacy policy", "follow us",
}


def from_html(html_str: str, url: str | None = None) -> str:
    """Main content from raw HTML → clean text. '' if nothing usable."""
    if not html_str:
        return ""
    try:
        import trafilatura
        txt = trafilatura.extract(
            html_str, url=url, include_comments=False, include_tables=True,
            favor_precision=True, no_fallback=False,
        )
        if txt and txt.strip():
            return txt.strip()
    except Exception:
        pass
    # fallback: strip chrome tags with bs4, then heuristically denoise
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_str, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                         "form", "noscript", "svg", "button"]):
            tag.decompose()
        return denoise_text(soup.get_text("\n"))
    except Exception:
        return ""


def denoise_text(text: str) -> str:
    """Heuristic cleanup of an innerText-style dump: collapse blank runs, drop short
    nav/boilerplate lines, dedupe consecutive repeats."""
    if not text:
        return ""
    out: list[str] = []
    prev = None
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            if out and out[-1] != "":
                out.append("")
            continue
        low = ln.lower()
        if low in _BOILER:
            continue
        # very short all-caps/title nav crumbs with no sentence content
        if len(ln) <= 2:
            continue
        if ln == prev:
            continue
        out.append(ln)
        prev = ln
    return "\n".join(out).strip()


def clean_capture(html_str: str | None = None, fallback_text: str | None = None,
                  url: str | None = None, min_chars: int = 200) -> str:
    """Best available clean text: extract from HTML if it yields real content,
    else denoise the fallback innerText. Returns at least the denoised fallback."""
    if html_str:
        main = from_html(html_str, url=url)
        if main and len(main) >= min_chars:
            return main
    return denoise_text(fallback_text or html_str or "")


def fetch_url(url: str) -> str:
    """Download a single article URL and return its clean main text. '' on failure.
    Pairs with news_rss: take a headline's link and read the body without the page chrome."""
    if not url:
        return ""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            txt = trafilatura.extract(downloaded, include_comments=False,
                                      include_tables=True, favor_precision=True)
            if txt and txt.strip():
                return txt.strip()
    except Exception:
        pass
    return ""


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        print(fetch_url(sys.argv[1]))
        raise SystemExit(0)
    data = sys.stdin.read()
    looks_html = "<html" in data.lower() or "<body" in data.lower() or "<div" in data.lower()
    print(clean_capture(html_str=data) if looks_html else denoise_text(data))
