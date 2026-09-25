"""Render docs/demo/synthetic_post.html (a synthetic social-media post) to docs/demo/synthetic_post.png."""

from pathlib import Path

from playwright.sync_api import sync_playwright

DEMO = Path(__file__).resolve().parent.parent / "docs" / "demo"

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 640, "height": 420}, device_scale_factor=1.5)
    page.goto((DEMO / "synthetic_post.html").as_uri())
    page.locator(".card").screenshot(path=DEMO / "synthetic_post.png")
    b.close()
print("ok", DEMO / "synthetic_post.png")
