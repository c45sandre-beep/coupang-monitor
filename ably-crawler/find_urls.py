"""로그인 후 주문·문의 페이지 탐색"""
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # 로그인
        await page.goto("https://my.a-bly.com/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="email"]', os.getenv("ABLY_EMAIL"))
        await page.fill('input[name="password"]', os.getenv("ABLY_PW"))
        await page.click('button:has-text("로그인")')
        await page.wait_for_timeout(4000)
        await page.screenshot(path=str(DEBUG_DIR / "after_login.png"), full_page=False)
        print(f"로그인 후 URL: {page.url}")

        # 메뉴 링크 수집
        links = await page.query_selector_all("a")
        print(f"\n전체 링크 {len(links)}개:")
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.text_content() or "").strip().replace("\n", " ")
            if text and href and href != "#":
                print(f"  '{text[:30]}' -> {href}")

        await browser.close()

asyncio.run(main())
