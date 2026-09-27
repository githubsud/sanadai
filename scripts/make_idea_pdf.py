"""Render docs/idea/idea.html (the challenge "idea file") to docs/idea/SanadAI_Idea_File.pdf with headless Chrome.

Chrome shapes Arabic correctly; dev tool: pip install playwright (uses the installed Chrome).
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

IDEA = Path(__file__).resolve().parent.parent / "docs" / "idea"

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page()
    page.goto((IDEA / "idea.html").as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(800)
    page.pdf(path=str(IDEA / "SanadAI_Idea_File.pdf"), format="A4", print_background=True, prefer_css_page_size=True)
    b.close()
print("ok", IDEA / "SanadAI_Idea_File.pdf")
