#!/usr/bin/env python3
"""Launches and owns the persistent "agent Chrome" browser used by the AI models.

Run as a systemd --user service (agent-browser.service) so it's always
available - shared/browser_client.py connects to it over CDP on port 9222
via Playwright's connect_over_cdp.

Plain subprocess launch (not Playwright-managed) because Playwright's
launch_persistent_context uses an internal pipe for its own control channel,
which suppresses Chrome's --remote-debugging-port TCP server. This is the
same command as the old manual launch, just supervised by systemd.

Uses the existing ~/.config/chrome-agent profile (cookies/logins persist
across restarts).
"""

import os
import signal
import subprocess
import sys

PROFILE_DIR = os.path.expanduser("~/.config/chrome-agent")
CDP_PORT = 9222


def main() -> None:
    proc = subprocess.Popen([
        "google-chrome",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        # Pin the profile (fixed 2026-08-25). The profile dir has grown three
        # profiles (Default, Profile 1, Profile 2); with none pinned Chrome
        # opened chrome://profile-picker/ instead of a page. The browser then
        # had ZERO page targets, so every browser_client._with_page() call fell
        # through to ctx.new_page() and spawned another tab.
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        # This box's RTX 2060 runs on nouveau, whose GL path (zink -> NVK) makes
        # the kernel kill Chrome's GPU channel ("Xid:13 Graphics Exception ...
        # WIDTH CT Violation" -> VK_ERROR_DEVICE_LOST -> GPU process exit 512),
        # which freezes the browser mid-render. Software rendering is stable.
        # Remove this if the proprietary NVIDIA driver is ever installed.
        "--disable-gpu",
        # This browser only scrapes. The on-device model stack pulled a 4 GB
        # download into the profile and started a TFLite delegate on every launch.
        "--disable-features=OptimizationGuideOnDeviceModel,TextSafetyClassifier",
    ])

    def handle_signal(*_args):
        proc.terminate()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print(f"agent-browser: launched Chrome (pid {proc.pid}) with CDP on port {CDP_PORT}, profile {PROFILE_DIR}")
    sys.exit(proc.wait())


if __name__ == "__main__":
    main()
