"""에이블리 인증 토큰 확인"""
import asyncio, os, json
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
BASE = "https://my.a-bly.com"

auth_headers = {}

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR", timezone_id="Asia/Seoul", viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        # 요청 헤더 캡처
        async def on_request(req):
            if "api.a-bly.com/seller" in req.url:
                hdrs = req.headers
                for k, v in hdrs.items():
                    if k.lower() in ("authorization", "x-auth-token", "token", "x-token", "x-access-token"):
                        auth_headers[k] = v

        page.on("request", on_request)

        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="email"]', os.getenv("ABLY_EMAIL"))
        await page.fill('input[name="password"]', os.getenv("ABLY_PW"))
        await page.click('button:has-text("로그인")')
        await page.wait_for_url(f"{BASE}/dashboard", timeout=15000)

        await page.goto(f"{BASE}/sales/order/prepare", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        print("인증 헤더:")
        for k, v in auth_headers.items():
            print(f"  {k}: {v[:80]}...")

        # localStorage/cookies 확인
        ls = await page.evaluate("JSON.stringify(localStorage)")
        ls_data = json.loads(ls)
        print("\nlocalStorage 키:")
        for k in ls_data:
            print(f"  {k}: {str(ls_data[k])[:80]}")

        cookies = await ctx.cookies()
        print("\n쿠키:")
        for c in cookies:
            if any(k in c['name'].lower() for k in ['token','auth','session','access']):
                print(f"  {c['name']}: {c['value'][:80]}")

        await browser.close()

asyncio.run(main())
