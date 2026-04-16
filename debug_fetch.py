"""홈페이지 컨텍스트에서 fetch()로 제품 페이지 요청"""
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import random, re, json

PROD_URL = "https://www.coupang.com/vp/products/9470756373?itemId=28188833809&vendorItemId=95134341815"

with Stealth().use_sync(sync_playwright()) as p:
    browser = p.chromium.launch(channel="chrome", headless=False)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()

    # 홈 로드
    print("홈 방문 + networkidle 대기...")
    page.goto("https://www.coupang.com", wait_until="networkidle", timeout=30000)

    # 사람처럼 행동
    for _ in range(5):
        page.mouse.move(random.randint(100,1100), random.randint(100,700))
        page.wait_for_timeout(random.randint(200,500))
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(2000)

    print("쿠키:", [c["name"] for c in context.cookies()])

    # 같은 origin에서 fetch로 제품 페이지 가져오기
    print("fetch() 요청...")
    result = page.evaluate(f"""
        async () => {{
            const res = await fetch("{PROD_URL}", {{
                headers: {{
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                }},
                credentials: "include",
            }});
            return {{
                status: res.status,
                html: await res.text(),
            }};
        }}
    """)

    status = result["status"]
    html   = result["html"]
    print(f"fetch status: {status} / size: {len(html):,}")

    if status == 200:
        # 데이터 파싱
        m = re.search(r"한\s*달간\s*([\d,]+)\s*명", html)
        print("구매자:", m.group() if m else "없음")

        m = re.search(r'"finalPrice"\s*:\s*"?([0-9,]+)"?', html)
        print("가격:", m.group(1) if m else "없음")

        m = re.search(r'"reviewCount"\s*:\s*([0-9]+)', html)
        print("리뷰:", m.group(1) if m else "없음")

        with open("C:/Users/KCW/scripts/debug_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML 저장됨")
    else:
        title = re.search(r'<title>(.*?)</title>', html, re.I)
        print("오류:", title.group(1) if title else html[:200])

    browser.close()
