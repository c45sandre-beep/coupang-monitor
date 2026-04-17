"""주문 API POST body 캡처"""
import asyncio, os, json
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

BASE = "https://shopping-seller.toss.im"

async def main():
    order_bodies = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        async def on_request(req):
            url = req.url
            if "shopping-order" in url or "biz-app-gateway" in url or "product/inquiry" in url:
                body_str = ""
                try:
                    body_str = req.post_data or ""
                except Exception:
                    pass
                order_bodies.append({
                    "method": req.method,
                    "url": url,
                    "body": body_str,
                    "headers": {k: v for k, v in req.headers.items()
                                if k.lower() not in ("cookie",)},
                })

        page.on("request", on_request)

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

        # 주문 페이지
        print("\n[2] 주문 페이지 로드...")
        order_bodies.clear()
        await page.goto(f"{BASE}/orders/order-management", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        print(f"  캡처된 요청 {len(order_bodies)}건:")
        for r in order_bodies:
            print(f"\n  {r['method']} {r['url']}")
            if r['body']:
                try:
                    parsed = json.loads(r['body'])
                    print(f"  body: {json.dumps(parsed, ensure_ascii=False, indent=2)}")
                except Exception:
                    print(f"  body: {r['body'][:300]}")
            print(f"  headers: { {k:v for k,v in r['headers'].items() if k.lower() not in ('user-agent','accept','sec-','origin','referer')} }")

        # 문의 페이지
        print("\n[3] 고객지원 페이지 로드...")
        order_bodies.clear()
        await page.goto(f"{BASE}/customer-support", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        print(f"  캡처된 요청 {len(order_bodies)}건:")
        for r in order_bodies:
            print(f"\n  {r['method']} {r['url']}")
            if r['body']:
                try:
                    parsed = json.loads(r['body'])
                    print(f"  body: {json.dumps(parsed, ensure_ascii=False, indent=2)}")
                except Exception:
                    print(f"  body: {r['body'][:300]}")

        # 쿠키
        cookies = await ctx.cookies()
        auth = {c["name"]: c["value"] for c in cookies
                if any(k in c["name"].lower() for k in ["token","auth","biz","session"])}
        print(f"\n[4] 인증 쿠키: {auth}")

        (DEBUG_DIR / "request_bodies.json").write_text(
            json.dumps(order_bodies, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n[완료]")
        await browser.close()

asyncio.run(main())
