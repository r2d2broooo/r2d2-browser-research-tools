"""Frame-by-frame recording of the agent-Chrome window.

There's no live video feed - instead this captures a burst of screenshots at
a fixed interval while the user performs a task, saved to disk in order.
Claude can then read through the frames sequentially (like flipping through
a flipbook) to see what the user did, step by step.
"""

import os
import time

from . import browser_client

RECORDINGS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "dashboard", "static", "recordings")
)

MAX_SECONDS = 120


async def record(seconds: int = 30, interval: float = 1.5) -> dict:
    seconds = max(1, min(seconds, MAX_SECONDS))
    interval = max(0.5, interval)

    session_id = time.strftime("%Y%m%d-%H%M%S")
    sdir = os.path.join(RECORDINGS_DIR, session_id)
    os.makedirs(sdir, exist_ok=True)

    frames = await browser_client.record_frames(seconds, interval, sdir)

    return {"session_id": session_id, "dir": sdir, "frames": frames}
