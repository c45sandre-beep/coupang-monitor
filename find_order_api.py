"""토스쇼핑 주문/문의 API 엔드포인트 탐색"""
import asyncio, os, json
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
DEBUG_DIR = Path(__file__).parent / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

BASE = "https://shopping-seller.toss.im"
all_requests = []
all_responses = []

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

        async def on_request(req):
            url = req.url
            if "toss.im" in url and req.resource_type in ("xhr", "fetch"):
                all_requests.append({
                    "method": req.method,
                    "url": url,
                    "headers": dict(req.headers),
                })

        async def on_response(resp):
            url = resp.url
            if "toss.im" in url and resp.status == 200:
                ct = resp.headers.get("content-type", "")
                if "json" in ct and resp.request.resource_type in ("xhr", "fetch"):
                    try:
                        body = await resp.json()
                        all_responses.append({"url": url, "body": body})
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
        await page.wait_for_timeout(6000)
        if "login" in page.url:
            print("로그인 실패!")
            await browser.close()
            return
        print(f"  성공: {page.url}")

        # 주문 페이지
        print("\n[2] 주문 페이지...")
        all_requests.clear(); all_responses.clear()
        await page.goto(f"{BASE}/order", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"  요청 {len(all_requests)}건, 응답 {len(all_responses)}건")
        for r in all_responses:
            print(f"  [응답] {r['url']}")
            print(f"         {json.dumps(r['body'], ensure_ascii=False)[:400]}\n")
        for r in all_requests:
            print(f"  [요청] {r['method']} {r['url']}")
            auth_hdrs = {k:v for k,v in r['headers'].items()
                        if k.lower() in ("authorization","x-merchant-id","x-auth-token","cookie")}
            if auth_hdrs:
                print(f"         헤더: {auth_hdrs}")

        await page.screenshot(path=str(DEBUG_DIR / "order_page.png"), full_page=True)

        # 문의 페이지
        print("\n[3] 문의 페이지...")
        all_requests.clear(); all_responses.clear()
        for path in ["/inquiry", "/inquiries", "/customer", "/qna", "/cs"]:
            try:
                await page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(2000)
                if "login" not in page.url:
                    print(f"  접근 가능: {page.url}")
                    for r in all_responses:
                        print(f"  [응답] {r['url']}")
                        print(f"         {json.dumps(r['body'], ensure_ascii=False)[:400]}\n")
                    await page.screenshot(path=str(DEBUG_DIR / f"inquiry_{path.replace('/','')}.png"))
                    break
            except Exception as e:
                print(f"  {path}: {e}")

        # 전체 메뉴 링크 수집
        print("\n[4] 메뉴 링크:")
        await page.goto(f"{BASE}/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        links = await page.query_selector_all("a[href]")
        seen = set()
        for link in links:
            href = await link.get_attribute("href") or ""
            txt = (await link.text_content() or "").strip().replace("\n", " ")[:30]
            if href and href not in seen and href.startswith("/"):
                seen.add(href)
                print(f"  '{txt}' -> {href}")

        # 결과 저장
        (DEBUG_DIR / "all_responses.json").write_text(
            json.dumps(all_responses, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (DEBUG_DIR / "all_requests.json").write_text(
            json.dumps(all_requests, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("\n[완료]")
        await browser.close()

asyncio.run(main())
