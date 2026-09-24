"""Capture UI screenshots into docs/screenshots with headless Chrome (dev tool: pip install playwright).

    python scripts/screenshots.py [home quran authentic weak fabricated]   # server must run on :8765
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
URL = "http://127.0.0.1:8765/"


def shoot(browser, width: int, tag: str, which: list[str]) -> list[str]:
    logs: list[str] = []
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
    page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
    page.goto(URL)
    page.wait_for_timeout(1500)
    if "home" in which:
        page.screenshot(path=OUT / f"01-home-{tag}.png")
    for ex in [x for x in which if x != "home"]:
        page.click(f'[data-example="{ex}"]')
        page.wait_for_selector("#results:not([hidden])", timeout=600_000)
        page.wait_for_timeout(3500)
        page.screenshot(path=OUT / f"02-{ex}-{tag}.png", full_page=True)
    if tag == "desktop" and which and which[-1] != "home":
        page.click("#prepareBtn")
        page.wait_for_timeout(2500)
        page.screenshot(path=OUT / f"03-prepare-{tag}.png")
    page.close()
    return [str(m) for m in logs]


def main() -> int:
    which = sys.argv[1:] or ["home", "quran", "authentic", "weak", "fabricated"]
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for width, tag in ((1280, "desktop"), (390, "mobile")):
            print(tag, "console:", shoot(browser, width, tag, which)[:10])
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
