import asyncio
from pathlib import Path
from dotenv import load_dotenv
import os
from playwright.async_api import async_playwright

load_dotenv()
COUPANG_ID = os.getenv("COUPANG_ID")
COUPANG_PW = os.getenv("COUPANG_PW")
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

async def set_input(page, field_name, value):
    escaped = value.replace("\\", "\\\\").replace("`", "\\`")
    await page.evaluate(f"""
        (() => {{
            const el = document.querySelector('input[name="{field_name}"]');
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, `{escaped}`);
            el.dispatchEvent(new Event('input',  {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }})()
    """)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR", timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # 로그인
        await page.goto("https://supplier.coupang.com/dashboard/KR", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.wait_for_selector('input[name="username"]', timeout=15000)
        await set_input(page, "username", COUPANG_ID)
        await set_input(page, "password", COUPANG_PW)
        await page.wait_for_timeout(500)
        await page.click('input[type="submit"], button[type="submit"]')
        await page.wait_for_url("https://supplier.coupang.com/**", timeout=20000)
        await page.wait_for_timeout(2000)
        print(f"[*] 로그인 성공: {page.url}")

        # Logistics 메뉴 클릭
        await page.click('text=Logistics')
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(DEBUG_DIR / "logistics_menu.png"), full_page=False)

        # 메뉴 링크 수집
        links = await page.query_selector_all("a")
        print("\n[Logistics 메뉴 링크]")
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.text_content() or "").strip()
            if text and href and href != "#":
                print(f"  '{text}' -> {href}")

        await browser.close()

asyncio.run(main())
