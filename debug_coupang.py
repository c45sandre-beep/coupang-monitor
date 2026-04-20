"""쿠팡 진단 - headless=False, 상호작용 시뮬레이션"""
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import random, re

URL = "https://www.coupang.com/vp/products/9470756373?itemId=28188833809&vendorItemId=95134341815"

with Stealth().use_sync(sync_playwright()) as p:
    browser = p.chromium.launch(
        channel="chrome",
        headless=False,         # 창이 실제로 보여야 함
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        viewport={"width": 1280, "height": 900},
        extra_http_headers={
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "sec-ch-ua": '"Chromium";v="124","Google Chrome";v="124","Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    )
    page = context.new_page()

    # 1단계: 홈 방문 + JS 완전 실행 대기
    print("홈 방문...")
    page.goto("https://www.coupang.com", wait_until="networkidle", timeout=30000)

    # 마우스 이동 (봇 아님을 증명)
    for _ in range(4):
        page.mouse.move(
            random.randint(200, 1000),
            random.randint(100, 700),
        )
        page.wait_for_timeout(random.randint(300, 700))

    page.mouse.wheel(0, random.randint(200, 500))
    page.wait_for_timeout(2000)

    print("홈 쿠키:", [c["name"] for c in context.cookies()])

    # 2단계: 제품 페이지
    print("제품 페이지 이동...")
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(5000)

    title = page.title()
    html  = page.content()
    print(f"title: {title} / size: {len(html):,}")

    # 데이터 추출 시도
    print("\n--- 구매자 수 ---")
    m = re.search(r"한\s*달간\s*([\d,]+)\s*명", html)
    if m: print("FOUND:", m.group())
    else: print("없음 / 관련 텍스트:", re.findall(r"구매[^<]{0,30}", html)[:3])

    print("\n--- 가격 ---")
    m = re.search(r'"finalPrice"\s*:\s*"?([0-9,]+)"?', html)
    if m: print("JSON finalPrice:", m.group(1))
    m2 = re.search(r'([0-9,]{4,})\s*원', html)
    if m2: print("first price:", m2.group())

    print("\n--- 리뷰 ---")
    m = re.search(r'"reviewCount"\s*:\s*([0-9]+)', html)
    if m: print("JSON reviewCount:", m.group(1))

    with open("C:/Users/KCW/scripts/debug_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 저장 완료: {len(html):,} bytes")

    input("Enter 누르면 브라우저 종료...")
    browser.close()
