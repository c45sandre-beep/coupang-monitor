"""Akamai 챌린지를 Chrome이 직접 해결하도록 기다리는 방식"""
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import re

URL = "https://www.coupang.com/vp/products/9470756373?itemId=28188833809&vendorItemId=95134341815"

with Stealth().use_sync(sync_playwright()) as p:
    browser = p.chromium.launch(
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()

    print("제품 페이지 직접 이동 (챌린지 대기)...")
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)

    # 챌린지 완료 후 실제 페이지 URL 또는 제목 변경까지 대기 (최대 20초)
    try:
        page.wait_for_function(
            "() => document.title !== '' && !document.title.includes('Access Denied') && document.title.length > 5",
            timeout=20000,
        )
    except:
        pass

    page.wait_for_timeout(3000)
    title = page.title()
    html  = page.content()
    print(f"title: {title} / size: {len(html):,}")

    if len(html) > 5000:
        m = re.search(r"한\s*달간\s*([\d,]+)\s*명", html)
        print("구매자:", m.group() if m else "없음")
        m = re.search(r'"finalPrice"\s*:\s*"?([0-9,]+)"?', html)
        print("가격:", m.group(1) if m else "없음")
        m = re.search(r'"reviewCount"\s*:\s*([0-9]+)', html)
        print("리뷰:", m.group(1) if m else "없음")

        with open("C:/Users/KCW/scripts/debug_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML 저장됨!")
    else:
        print("페이지 로드 실패. HTML 일부:", html[:300])

    browser.close()
