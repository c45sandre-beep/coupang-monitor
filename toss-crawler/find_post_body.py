"""Playwright route interceptor로 POST body 캡처"""
import asyncio, os, json
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
BASE = "https://shopping-seller.toss.im"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # route 인터셉터로 POST body 캡처
        async def intercept(route):
            req = route.request
            url = req.url
            if "shopping-order" in url or "biz-app-gateway" in url or "status-count" in url:
                body = req.post_data
                print(f"\n[인터셉트] {req.method} {url}")
                if body:
                    try:
                        print(f"  body: {json.dumps(json.loads(body), ensure_ascii=False, indent=2)}")
                    except Exception:
                        print(f"  body(raw): {body[:500]}")
                else:
                    print(f"  body: (없음)")
            await route.continue_()

        await page.route("**/*", intercept)

        # 로그인
        print("[1] 로그인...")
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="username"]', os.getenv("TOSS_EMAIL", ""))
        await page.fill('input[name="password"]', os.getenv("TOSS_PW", ""))
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(6000)
        if "login" in page.url:
            print("로그인 실패!")
            await browser.close()
            return
        print(f"  성공: {page.url}")

        print("\n[2] 주문 페이지...")
        await page.goto(f"{BASE}/orders/order-management", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        print("\n[3] 고객지원 페이지...")
        await page.goto(f"{BASE}/customer-support", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        print("\n[완료]")
        await browser.close()

asyncio.run(main())
