import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

DEBUG_DIR = Path(__file__).parent / "debug"

async def main():
    DEBUG_DIR.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        # navigator.webdriver 숨기기
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        await page.goto("https://wing.coupang.com/login", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)

        # 스크린샷 저장
        await page.screenshot(path=str(DEBUG_DIR / "login_page.png"), full_page=True)

        # 모든 input 태그 출력
        inputs = await page.query_selector_all("input")
        print(f"input 태그 {len(inputs)}개 발견:")
        for i, inp in enumerate(inputs):
            name   = await inp.get_attribute("name") or ""
            id_    = await inp.get_attribute("id") or ""
            type_  = await inp.get_attribute("type") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            print(f"  [{i}] name={name!r} id={id_!r} type={type_!r} placeholder={placeholder!r}")

        # 현재 URL
        print(f"\n현재 URL: {page.url}")

        html = await page.content()
        (DEBUG_DIR / "login_page.html").write_text(html, encoding="utf-8")
        print("\ndebug/login_page.png 와 debug/login_page.html 저장 완료")
        await browser.close()

asyncio.run(main())
