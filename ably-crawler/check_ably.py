"""에이블리 파트너센터 페이지 구조 확인"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

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

        await page.goto("https://my.a-bly.com", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(DEBUG_DIR / "ably_main.png"), full_page=False)
        print(f"현재 URL: {page.url}")

        inputs = await page.query_selector_all("input")
        print(f"\ninput 태그 {len(inputs)}개:")
        for i, inp in enumerate(inputs):
            print(f"  [{i}] name={await inp.get_attribute('name')!r} id={await inp.get_attribute('id')!r} type={await inp.get_attribute('type')!r} placeholder={await inp.get_attribute('placeholder')!r}")

        buttons = await page.query_selector_all("button")
        print(f"\nbutton 태그 {len(buttons)}개:")
        for i, btn in enumerate(buttons[:10]):
            print(f"  [{i}] type={await btn.get_attribute('type')!r} text={((await btn.text_content()) or '').strip()[:40]!r}")

        (DEBUG_DIR / "ably_main.html").write_text(await page.content(), encoding="utf-8")
        await browser.close()

asyncio.run(main())
