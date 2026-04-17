"""주문/문의 페이지 구조 확인"""
import asyncio, os, re
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

BASE = "https://my.a-bly.com"

async def snap(page, url, label):
    await page.goto(f"{BASE}{url}", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await page.screenshot(path=str(DEBUG_DIR / f"{label}.png"), full_page=True)
    html = await page.content()
    (DEBUG_DIR / f"{label}.html").write_text(html, encoding="utf-8")
    print(f"[{label}] URL: {page.url}")

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="email"]', os.getenv("ABLY_EMAIL"))
        await page.fill('input[name="password"]', os.getenv("ABLY_PW"))
        await page.click('button:has-text("로그인")')
        await page.wait_for_url(f"{BASE}/dashboard", timeout=15000)
        print("로그인 성공")

        await snap(page, "/sales/order/prepare", "order_prepare")
        await snap(page, "/sales/order",         "order_all")
        await snap(page, "/inquiry",             "inquiry")

        await browser.close()

asyncio.run(main())
