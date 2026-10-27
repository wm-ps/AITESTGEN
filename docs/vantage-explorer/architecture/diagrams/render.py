"""Render every <section class="fig"> in figures.html to img/<id>.png.

Run from the repo root:
    .venv/Scripts/python.exe docs/vantage-explorer/architecture/diagrams/render.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "img"

OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1300, "height": 900}, device_scale_factor=2)
    page.goto((HERE / "figures.html").as_uri())
    page.wait_for_timeout(500)
    for fig in page.locator("section.fig").all():
        name = fig.get_attribute("id")
        fig.screenshot(path=str(OUT / f"{name}.png"))
        print(f"img/{name}.png")
    browser.close()
