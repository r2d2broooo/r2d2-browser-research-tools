"""Desktop automation primitives: screenshots + mouse/keyboard control via X11.

Runs on the real desktop session (DISPLAY=:0), so it sees/controls whatever
is actually on screen - including the user's real, logged-in Chrome window.
"""

import subprocess
import time

DISPLAY = ":0"


def _run(cmd: list[str], timeout: int = 15) -> str:
    result = subprocess.run(
        cmd,
        env={"DISPLAY": DISPLAY, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def screenshot() -> bytes:
    """Capture the full desktop as PNG bytes."""
    result = subprocess.run(
        ["import", "-window", "root", "png:-"],
        env={"DISPLAY": DISPLAY, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        timeout=15,
    )
    return result.stdout


def find_chrome_window() -> str | None:
    out = _run(["xdotool", "search", "--onlyvisible", "--class", "chrome"])
    ids = out.splitlines()
    return ids[-1] if ids else None


def focus_chrome() -> bool:
    win = find_chrome_window()
    if not win:
        return False
    _run(["xdotool", "windowactivate", win])
    time.sleep(0.3)
    return True


def click(x: int, y: int) -> None:
    _run(["xdotool", "mousemove", str(x), str(y)])
    _run(["xdotool", "click", "1"])


def type_text(text: str) -> None:
    _run(["xdotool", "type", "--clearmodifiers", "--delay", "20", text])


def key(combo: str) -> None:
    """Send a key or key combo, e.g. 'Return', 'ctrl+l', 'Page_Down'."""
    _run(["xdotool", "key", "--clearmodifiers", combo])


def navigate(url: str) -> bool:
    """Focus Chrome, open a new tab, and load url via the address bar."""
    if not focus_chrome():
        return False
    key("ctrl+t")
    time.sleep(0.3)
    type_text(url)
    key("Return")
    time.sleep(1.5)
    return True


def scroll(direction: str = "down", amount: int = 5) -> None:
    button = "5" if direction == "down" else "4"
    for _ in range(amount):
        _run(["xdotool", "click", button])
