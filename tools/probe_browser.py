# -*- coding: utf-8 -*-
"""One vetted headless browser for the mandatory live-DOM checks (tracker ID 401).

WHY THIS EXISTS
    Every Streamlit change in this repo has to be verified in a real browser before it counts
    as done -- the rule exists because the same broken UI fix shipped twice on the strength of
    py_compile and curl. That means a browser launch per change, and each probe script had
    been rolling its own with different flags and its own cleanup. This centralises the flag
    set and, more importantly, guarantees the browser is CLOSED: a leaked headless chromium
    holds ~375 MB indefinitely and nobody notices until the machine is short of memory.

WHY CHROMIUM AND NOT WEBKIT
    WebKit is roughly half the memory and it is the wrong tool. The check exists to catch what
    the USER'S browser renders, and they use Chrome. A check that passes under WebKit and
    fails in Chrome is worse than no check, because it is a green light that means nothing.

FLAGS: WHAT IS HERE AND WHAT IS DELIBERATELY NOT
    Most "reduce Playwright memory" advice online is written for Docker/CI on Linux and does
    not transfer to a Windows desktop. Two widely-copied flags are omitted on purpose:

      --disable-dev-shm-usage      A Docker workaround. It redirects Chrome's shared memory
                                   from /dev/shm (capped at 64 MB in containers) to /tmp.
                                   Windows has no /dev/shm, so it buys nothing here and the
                                   Playwright docs warn it trades crashes for slower loads.
      --disable-gl-drawing-for-tests
                                   The single biggest memory win, and unusable for us: it
                                   stops the renderer actually drawing. Streamlit grids are
                                   CANVAS-rendered, so our probes read them from screenshots.
                                   This flag would leave those screenshots blank -- passing
                                   the probe while showing nothing, the exact failure the
                                   whole rule was written to prevent.

      --no-sandbox                 A container concern. On a desktop it lowers the sandbox for
                                   no measured gain, so it is not worth the trade even against
                                   localhost.

    What remains is the part that genuinely applies to a headless desktop run.
"""
from contextlib import contextmanager

# Measured against the real dashboard on 2026-09-03: 375 MB default -> 334 MB with these.
LEAN_ARGS = [
    "--disable-gpu",                       # no display to accelerate to
    "--disable-software-rasterizer",       # do not fall back to a CPU rasteriser either
    "--disable-extensions",
    "--disable-background-networking",     # no update pings, no field trials
    "--disable-background-timer-throttling",
    "--disable-breakpad",                  # no crash reporter process
    "--disable-features=TranslateUI,site-per-process",   # one renderer, not one per frame
    "--renderer-process-limit=1",
    "--js-flags=--max-old-space-size=256",
    "--mute-audio",
]


@contextmanager
def probe_page(width=1600, height=1200, engine="chromium"):
    """Yield a Playwright page with the vetted flags; always closes, even on exception.

    The `finally` is the point. A probe that raises mid-check -- a timeout, a bad selector --
    used to leave the browser resident, and those are exactly the runs where someone stops to
    debug and forgets the process.
    """
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = None
    try:
        browser = getattr(pw, engine).launch(args=LEAN_ARGS)
        page = browser.new_page(viewport={"width": width, "height": height})
        yield page
    finally:
        try:
            if browser:
                browser.close()
        finally:
            pw.stop()
