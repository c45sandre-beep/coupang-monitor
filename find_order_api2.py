"""토스쇼핑 주문/문의 실제 API 캡처 (모든 네트워크 요청)"""
import asyncio, os, json, sys
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

BASE = "https://shopping-seller.toss.im"

async def main():
    all_req = []
    all_resp = []

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

        # 모든 네트워크 요청 캡처 (resource type 무관)
        async def on_request(req):
            url = req.url
            if "toss.im" in url and "google" not in url and "analytics" not in url:
                all_req.append({
                    "method": req.method,
                    "url": url,
                    "type": req.resource_type,
                    "headers": {k: v for k, v in req.headers.items()
                                if k.lower() not in ("cookie",)},
                })

        async def on_response(resp):
            url = resp.url
            if "toss.im" in url and "google" not in url and "analytics" not in url:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        body = await resp.json()
                        all_resp.append({"url": url, "status": resp.status, "body": body})
                    except Exception:
                        pass

        page.on("request", on_request)
        page.on("response", on_response)

        # 로그인
        print("[1] 로그인...")
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="username"]', os.getenv("TOSS_EMAIL", ""))
        await page.fill('input[name="password"]', os.getenv("TOSS_PW", ""))
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(7000)
        if "login" in page.url:
            print("로그인 실패!")
            await browser.close()
            return
        print(f"  성공: {page.url}")

        # ── 주문관리 페이지 ──────────────────────
        print("\n[2] /orders/order-management")
        all_req.clear(); all_resp.clear()
        await page.goto(f"{BASE}/orders/order-management", wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
        print(f"  URL: {page.url}")
        print(f"  JSON 응답 {len(all_resp)}건:")
        for r in all_resp:
            body_s = json.dumps(r["body"], ensure_ascii=False)[:500]
            print(f"    [{r['status']}] {r['url']}")
            print(f"    {body_s}\n")
        print(f"  전체 요청 {len(all_req)}건 (non-analytics, toss.im):")
        for r in all_req:
            if r["type"] not in ("image", "stylesheet", "font", "script", "ping"):
                print(f"    {r['method']} {r['url']} [{r['type']}]")

        await page.screenshot(path=str(DEBUG_DIR / "order_mgmt.png"), full_page=True)
        html = await page.content()
        (DEBUG_DIR / "order_mgmt.html").write_text(html, encoding="utf-8")

        # ── 고객지원 페이지 ──────────────────────
        print("\n[3] /customer-support")
        all_req.clear(); all_resp.clear()
        await page.goto(f"{BASE}/customer-support", wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
        print(f"  URL: {page.url}")
        print(f"  JSON 응답 {len(all_resp)}건:")
        for r in all_resp:
            body_s = json.dumps(r["body"], ensure_ascii=False)[:500]
            print(f"    [{r['status']}] {r['url']}")
            print(f"    {body_s}\n")
        print(f"  전체 요청 {len(all_req)}건:")
        for r in all_req:
            if r["type"] not in ("image", "stylesheet", "font", "script", "ping"):
                print(f"    {r['method']} {r['url']} [{r['type']}]")

        # ── 인증 정보 저장 ──────────────────────
        cookies = await ctx.cookies()
        auth_cookies = {c["name"]: c["value"] for c in cookies
                       if any(k in c["name"].lower() for k in
                              ["token","auth","session","access","jwt","seller","biz","merchant"])}
        print(f"\n[4] 인증 쿠키: {list(auth_cookies.keys())}")
        for k, v in auth_cookies.items():
            print(f"  {k}: {v[:80]}")

        (DEBUG_DIR / "auth_cookies.json").write_text(
            json.dumps(auth_cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print("\n[완료]")
        await browser.close()

asyncio.run(main())
