"""에이블리 API 응답 인터셉트"""
import asyncio, os, json, re
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)
BASE = "https://my.a-bly.com"

captured = []

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # API 응답 캡처
        async def on_response(resp):
            url = resp.url
            if any(k in url for k in ["order", "inquiry", "question", "qna"]):
                try:
                    body = await resp.json()
                    captured.append({"url": url, "body": body})
                except Exception:
                    pass

        page.on("response", on_response)

        # 로그인
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="email"]', os.getenv("ABLY_EMAIL"))
        await page.fill('input[name="password"]', os.getenv("ABLY_PW"))
        await page.click('button:has-text("로그인")')
        await page.wait_for_url(f"{BASE}/dashboard", timeout=15000)
        print("로그인 성공")

        # 주문 페이지
        print("\n[주문 페이지]")
        captured.clear()
        await page.goto(f"{BASE}/sales/order/prepare", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        for c in captured:
            print(f"  API: {c['url']}")
            body_str = json.dumps(c['body'], ensure_ascii=False)[:300]
            print(f"  응답: {body_str}\n")

        # 문의 페이지
        print("\n[문의 페이지]")
        captured.clear()
        await page.goto(f"{BASE}/inquiry", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        for c in captured:
            print(f"  API: {c['url']}")
            body_str = json.dumps(c['body'], ensure_ascii=False)[:300]
            print(f"  응답: {body_str}\n")

        await browser.close()

asyncio.run(main())
