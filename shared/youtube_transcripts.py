"""YouTube transcripts — pull the spoken text out of a video (e.g. an earnings call).

Earnings calls, management interviews and analyst-day talks live on YouTube as video; the
words are what matter. This grabs the caption track (manual if present, else auto), turns it
into clean plain text, and can search for a company's latest earnings-call upload. Feeds the
holistic analysis + the Trading Wiki (primary-source quotes from management).

Uses yt-dlp (already a dep). No download of the actual media — captions only.
"""
from __future__ import annotations

import json
import re
import urllib.request

import yt_dlp

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "writesubtitles": True,
    "writeautomaticsub": True,
    "subtitleslangs": ["en", "en-US", "en-GB"],
}


def _video_id(url_or_id: str) -> str:
    s = (url_or_id or "").strip()
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    return s  # let yt-dlp try to resolve whatever it is


def _pick_caption(tracks: dict) -> list | None:
    """From a {lang: [formats]} dict, return the formats list for the best English track."""
    if not tracks:
        return None
    for lang in ("en", "en-US", "en-GB"):
        if tracks.get(lang):
            return tracks[lang]
    # any en* variant (auto-translations look like 'en-x-...')
    for lang, fmts in tracks.items():
        if lang.lower().startswith("en") and fmts:
            return fmts
    return None


def _download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _parse_json3(raw: str) -> str:
    """YouTube json3 caption format → text."""
    data = json.loads(raw)
    out = []
    for ev in data.get("events", []):
        segs = ev.get("segs") or []
        line = "".join(s.get("utf8", "") for s in segs).strip()
        if line:
            out.append(line)
    return _dedupe("\n".join(out))


def _parse_vtt(raw: str) -> str:
    """WebVTT/SRT-ish caption text → text (drop timestamps, cue numbers, tags)."""
    out = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if (not ln or ln == "WEBVTT" or "-->" in ln or ln.isdigit()
                or ln.startswith(("Kind:", "Language:", "NOTE"))):
            continue
        ln = re.sub(r"<[^>]+>", "", ln)  # inline timing tags
        if ln:
            out.append(ln)
    return _dedupe("\n".join(out))


def _dedupe(text: str) -> str:
    """Auto-captions repeat each line as a rolling overlay — drop consecutive dupes."""
    out, prev = [], None
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and ln != prev:
            out.append(ln)
            prev = ln
    return "\n".join(out)


def _caption_text(formats: list) -> str:
    """Pick the easiest-to-parse caption format from a track and return its text."""
    by_ext = {f.get("ext"): f for f in formats if f.get("url")}
    if "json3" in by_ext:
        try:
            return _parse_json3(_download(by_ext["json3"]["url"]))
        except Exception:
            pass
    for ext in ("vtt", "srv1", "srv2", "srv3", "ttml"):
        if ext in by_ext:
            try:
                return _parse_vtt(_download(by_ext[ext]["url"]))
            except Exception:
                continue
    # last resort: first available
    for f in formats:
        if f.get("url"):
            try:
                raw = _download(f["url"])
                return _parse_json3(raw) if raw.lstrip().startswith("{") else _parse_vtt(raw)
            except Exception:
                continue
    return ""


def fetch_transcript(url_or_id: str, max_chars: int = 40000) -> dict:
    """Return {ok, id, title, channel, duration_s, kind, text, error} for one video.
    kind is 'manual' (human subtitles) or 'auto' (machine captions)."""
    vid = _video_id(url_or_id)
    out = {"ok": False, "id": vid, "title": "", "channel": "", "duration_s": None,
           "kind": "", "text": "", "error": ""}
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except Exception as e:
        out["error"] = f"lookup failed: {e}"
        return out
    out["title"] = info.get("title", "")
    out["channel"] = info.get("uploader") or info.get("channel") or ""
    out["duration_s"] = info.get("duration")
    manual = _pick_caption(info.get("subtitles") or {})
    auto = _pick_caption(info.get("automatic_captions") or {})
    track, kind = (manual, "manual") if manual else (auto, "auto")
    if not track:
        out["error"] = "no English captions (manual or auto) available"
        return out
    text = _caption_text(track)
    if not text:
        out["error"] = "captions found but could not be downloaded/parsed"
        return out
    out.update(ok=True, kind=kind, text=text[:max_chars])
    return out


def search_youtube(query: str, n: int = 5) -> list[dict]:
    """Search YouTube; return up to n {id, title, channel, duration_s, url} (no captions)."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    except Exception:
        return []
    items = []
    for e in (info or {}).get("entries", []) or []:
        if not e:
            continue
        items.append({
            "id": e.get("id"),
            "title": e.get("title", ""),
            "channel": e.get("uploader") or e.get("channel") or "",
            "duration_s": e.get("duration"),
            "url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id')}",
        })
    return items


def _dur(secs) -> str:
    if not secs:
        return "?"
    secs = int(secs)
    h, m = secs // 3600, (secs % 3600) // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"


def earnings_call_transcript(ticker: str, max_chars: int = 40000) -> dict:
    """Find the most likely recent earnings-call video for a ticker and transcribe it.
    Returns the fetch_transcript dict plus 'picked' (the chosen search hit) and
    'candidates'."""
    t = ticker.upper().strip()
    hits = search_youtube(f"{t} earnings call", n=6)
    # prefer titles that actually look like an earnings call, longest first (calls run ~1h)
    def score(h):
        title = (h.get("title") or "").lower()
        s = 0
        if "earnings call" in title:
            s += 3
        elif "earnings" in title:
            s += 1
        if any(q in title for q in ("q1", "q2", "q3", "q4", "fy", "20")):
            s += 1
        if (h.get("duration_s") or 0) >= 1200:  # >=20 min reads like a real call
            s += 1
        return s
    ranked = sorted(hits, key=score, reverse=True)
    if not ranked:
        return {"ok": False, "error": f"no YouTube results for '{t} earnings call'",
                "picked": None, "candidates": []}
    picked = ranked[0]
    res = fetch_transcript(picked["url"], max_chars=max_chars)
    res["picked"] = picked
    res["candidates"] = ranked
    return res


def transcript_text(url_or_id: str, max_chars: int = 40000) -> str:
    """Human/LLM-readable transcript block for one video."""
    r = fetch_transcript(url_or_id, max_chars=max_chars)
    if not r["ok"]:
        return f"YOUTUBE TRANSCRIPT — {r['id']}: (unavailable — {r['error']})"
    head = (f"YOUTUBE TRANSCRIPT — {r['title']}\n"
            f"[channel={r['channel']} · {_dur(r['duration_s'])} · captions={r['kind']} · "
            f"id={r['id']}]")
    return f"{head}\n\n{r['text']}"


def earnings_call_text(ticker: str, max_chars: int = 40000) -> str:
    """Human/LLM-readable earnings-call transcript block for a ticker."""
    r = earnings_call_transcript(ticker, max_chars=max_chars)
    t = ticker.upper().strip()
    if not r.get("picked"):
        return f"EARNINGS CALL — {t}: (no candidate video found)"
    p = r["picked"]
    head = (f"EARNINGS CALL (YouTube) — {t}\n"
            f"[picked: {p['title']!r} · {p['channel']} · {_dur(p.get('duration_s'))} · "
            f"{p['url']}]")
    if not r["ok"]:
        alts = "\n".join(f"  - {c['title']} ({_dur(c.get('duration_s'))}) {c['url']}"
                         for c in r.get("candidates", [])[:5])
        return f"{head}\n(transcript unavailable — {r['error']})\nother candidates:\n{alts}"
    return f"{head}\n[captions={r['kind']}]\n\n{r['text']}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: youtube_transcripts.py <video-url|video-id> | --call TICKER | "
              "--search QUERY")
        raise SystemExit(2)
    if sys.argv[1] == "--call":
        print(earnings_call_text(sys.argv[2]))
    elif sys.argv[1] == "--search":
        for h in search_youtube(" ".join(sys.argv[2:]), n=6):
            print(f"- {h['title']}  ({_dur(h.get('duration_s'))})  {h['url']}")
    else:
        print(transcript_text(sys.argv[1]))
