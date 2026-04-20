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

async def set_input(page, field_id, value):
    escaped = value.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("!", "\\!")
    await page.evaluate(f"""
        (() => {{
            const el = document.getElementById('{field_id}');
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

        await page.goto("https://supplier.coupang.com/dashboard/KR", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        await page.screenshot(path=str(DEBUG_DIR / "supplier_redirect.png"), full_page=True)
        print(f"현재 URL: {page.url}")

        # 로그인 폼 입력 필드 전체 출력
        inputs = await page.query_selector_all("input")
        print(f"input 태그 {len(inputs)}개:")
        for i, inp in enumerate(inputs):
            print(f"  [{i}] name={await inp.get_attribute('name')!r} id={await inp.get_attribute('id')!r} type={await inp.get_attribute('type')!r}")

        await page.wait_for_selector('#username', timeout=15000)
        await set_input(page, "username", COUPANG_ID)
        await set_input(page, "password", COUPANG_PW)
        await page.wait_for_timeout(500)
        await page.click('#kc-login')
        await page.wait_for_url("https://supplier.coupang.com/**", timeout=20000)
        print(f"[*] 로그인 성공: {page.url}")

        # 홈 스크린샷
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(DEBUG_DIR / "home.png"), full_page=True)
        print("[*] 홈 스크린샷 저장")

        # 발주 관련 링크 탐색
        links = await page.query_selector_all("a")
        order_links = []
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.text_content() or "").strip()
            if any(kw in text for kw in ["발주", "구매", "주문", "PO", "purchase"]):
                order_links.append(f"text='{text}' href='{href}'")

        print("\n[발주 관련 링크]")
        for l in order_links:
            print(" ", l)

        # 사이드 메뉴 텍스트 전체 출력
        print("\n[전체 메뉴 링크]")
        for link in links[:50]:
            href = await link.get_attribute("href") or ""
            text = (await link.text_content() or "").strip()
            if href and text:
                print(f"  text='{text}' href='{href}'")

        await browser.close()

asyncio.run(main())
