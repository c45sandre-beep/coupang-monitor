"""모바일 URL로 Akamai 챌린지 통과 시도"""
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import re

MOB_URL = "https://m.coupang.com/vm/products/9470756373?itemId=28188833809&vendorItemId=95134341815"

with Stealth().use_sync(sync_playwright()) as p:
    browser = p.chromium.launch(
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Linux; Android 13; SM-S918B) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/112.0.0.0 Mobile Safari/537.36"
        ),
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        viewport={"width": 390, "height": 844},
        is_mobile=True,
    )
    page = context.new_page()

    print("모바일 제품 페이지 이동 (챌린지 대기 최대 30초)...")
    page.goto(MOB_URL, wait_until="domcontentloaded", timeout=30000)

    # 챌린지 통과 후 실제 제품 페이지로 reload될 때까지 대기
    for i in range(30):
        page.wait_for_timeout(1000)
        title = page.title()
        html  = page.content()
        size  = len(html)
        print(f"  {i+1}s: title={repr(title[:40])} size={size}")
        if size > 10000 and "Access Denied" not in title:
            print("✅ 페이지 로드 성공!")
            break
    else:
        print("❌ 30초 내 챌린지 통과 실패")

    html = page.content()
    print(f"\n최종 size: {len(html):,}")

    if len(html) > 10000:
        m = re.search(r"한\s*달간\s*([\d,]+)\s*명", html)
        print("구매자:", m.group() if m else "없음")
        m = re.search(r'"finalPrice"\s*:\s*"?([0-9,]+)"?', html)
        print("가격:", m.group(1) if m else "없음")
        m = re.search(r'"reviewCount"\s*:\s*([0-9]+)', html)
        print("리뷰:", m.group(1) if m else "없음")

        with open("C:/Users/KCW/scripts/debug_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML 저장됨!")

    browser.close()
