"""토스쇼핑 파트너센터 API 탐색"""
import asyncio, os, json
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

BASE = "https://shopping-seller.toss.im"
captured_api = []

async def main():
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

        # 모든 API 응답 캡처
        async def on_response(resp):
            url = resp.url
            if "toss.im" in url and resp.status == 200:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        body = await resp.json()
                        captured_api.append({"url": url, "body": body})
                    except Exception:
                        pass

        # 모든 요청 헤더 캡처
        auth_info = {}
        async def on_request(req):
            url = req.url
            if "toss.im" in url:
                hdrs = req.headers
                for k, v in hdrs.items():
                    if k.lower() in ("authorization", "x-auth-token", "token",
                                     "x-token", "x-access-token", "x-toss-token",
                                     "x-merchant-id", "merchant-id"):
                        auth_info[k] = v

        page.on("response", on_response)
        page.on("request", on_request)

        # 로그인
        print("[1] 로그인 중...")
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="username"]', os.getenv("TOSS_EMAIL", ""))
        await page.fill('input[name="password"]', os.getenv("TOSS_PW", ""))
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(6000)
        print(f"  로그인 후 URL: {page.url}")
        await page.screenshot(path=str(DEBUG_DIR / "01_after_login.png"))

        if "login" in page.url:
            print("  [!] 로그인 실패 - URL이 여전히 login 페이지")
            await browser.close()
            return

        print("  로그인 성공!")

        # 주문 페이지 탐색
        print("\n[2] 주문 페이지 탐색")
        captured_api.clear()
        await page.goto(f"{BASE}/order", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        print(f"  URL: {page.url}")
        await page.screenshot(path=str(DEBUG_DIR / "02_order.png"))
        html = await page.content()
        (DEBUG_DIR / "02_order.html").write_text(html, encoding="utf-8")

        print(f"  캡처된 API {len(captured_api)}건:")
        for c in captured_api:
            body_str = json.dumps(c["body"], ensure_ascii=False)[:300]
            print(f"    {c['url']}")
            print(f"    -> {body_str}\n")

        # 인증 헤더
        print(f"\n[3] 인증 헤더 {len(auth_info)}개:")
        for k, v in auth_info.items():
            print(f"  {k}: {v[:100]}")

        # 쿠키
        cookies = await ctx.cookies()
        print(f"\n[4] 인증 쿠키:")
        for c in cookies:
            if any(k in c["name"].lower() for k in ["token","auth","session","access","jwt","seller","merchant"]):
                print(f"  {c['name']}: {c['value'][:100]}")

        # localStorage
        ls = json.loads(await page.evaluate("JSON.stringify(localStorage)"))
        print(f"\n[5] localStorage:")
        for k, v in ls.items():
            print(f"  {k}: {str(v)[:100]}")

        # 결과 저장
        (DEBUG_DIR / "captured_api.json").write_text(
            json.dumps(captured_api, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (DEBUG_DIR / "auth_info.json").write_text(
            json.dumps({"headers": auth_info, "cookies": [
                {"name": c["name"], "value": c["value"]} for c in cookies
            ]}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print("\n[완료] debug/ 폴더에 결과 저장됨")
        await page.wait_for_timeout(3000)
        await browser.close()

asyncio.run(main())
