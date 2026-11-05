# R2D2 Browser Research Tools

Small Python helpers for browser automation, article extraction, video captions and local capture. They let a research or coding workflow choose between a lightweight static fetch and an interactive browser instead of launching a full browser for every document.

The toolkit is independent of the trading system and agent memory store. It starts no AI model and ships no logged-in browser profile.

## Included modules

| Module | What it does |
|---|---|
| `shared/browser_client.py` | Connects Playwright to an existing Chrome/CDP session; reads pages, navigates, uses selectors, captures screenshots and lists tabs |
| `shared/agent_browser.py` | Launches a dedicated local Chrome profile with remote debugging |
| `shared/scrape_client.py` | Fetches static page content through Scrapling |
| `shared/clean_extract.py` | Extracts article text and reduces boilerplate from captured HTML/text |
| `shared/youtube_transcripts.py` | Retrieves available captions and normalizes supported caption formats |
| `shared/desktop.py` | Provides Linux/X11 screenshot and input fallbacks |
| `shared/screen_recorder.py` | Captures a sequence of local browser frames |

Selector-based browser operations use the browser's own session; they do not extract or export authentication cookies. Desktop input affects the active desktop and should be used deliberately.

## Setup

Use a separate Python environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python3 check.py
```

Interactive operations require Chrome with CDP available on `localhost` at the configured debugging port. Review `shared/agent_browser.py` for the profile directory, Chrome executable and launch options. The optional systemd example assumes a particular clone/venv layout; edit it for your installation before enabling it. Nothing installs or enables that service automatically.

Static extraction can be used without starting Chrome:

```python
from shared.clean_extract import from_html

text = from_html("<article><h1>Example</h1><p>Locally supplied content.</p></article>")
```

The asynchronous browser APIs include `goto`, `read_page`, `screenshot_url`, `click`, `fill`, `press_key` and `list_tabs`. Read their module docstrings before integrating them into a larger application.

## Privacy and limits

Your browser logins, downloads, screenshots and recordings remain local and are not part of this repository. A screenshot or caption may contain private or copyrighted material even though this toolkit's source does not. Decide what may leave the machine in the calling workflow.

Captions depend on what the source makes available; extraction does not guarantee access to every page or video. Desktop fallbacks need Linux/X11 utilities. The automated source checks do not authenticate a site, submit forms, send messages or confirm an external service's availability. See [USAGE.md](USAGE.md) for integration notes.

## Privacy, provenance and updates

This repository is a sanitized source export. No provider credentials, personal contact information, configured IP addresses, private conversations or runtime databases are included. Example hostnames and local environment variables are intentional. Keep newly generated account data and captures outside version control.

A source manifest records exported files. Local adaptations and third-party material retain their own provenance/notices; public visibility does not apply a new blanket license to every file. Related repositories and the manual update process are listed in the [workspace catalogue](https://github.com/r2d2broooo/r2d2-workspace-catalog).

Updates are made only on explicit request. Cloning does not enable an automatic sync, scheduled publication or Git push.
