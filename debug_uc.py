"""undetected-chromedriver 테스트"""
import undetected_chromedriver as uc
import time, random, re

URL = "https://www.coupang.com/vp/products/9470756373?itemId=28188833809&vendorItemId=95134341815"

options = uc.ChromeOptions()
options.add_argument("--lang=ko-KR")
options.add_argument("--window-size=1280,900")

driver = uc.Chrome(options=options, headless=False)

try:
    # 홈 방문
    print("홈 방문...")
    driver.get("https://www.coupang.com")
    time.sleep(3 + random.uniform(0.5, 1.5))

    # 제품 페이지
    print("제품 페이지 이동...")
    driver.get(URL)
    time.sleep(5 + random.uniform(1, 2))

    title = driver.title
    html  = driver.page_source
    print(f"title: {title} / size: {len(html):,}")

    # 데이터 추출
    print("\n--- 구매자 수 ---")
    m = re.search(r"한\s*달간\s*([\d,]+)\s*명\s*이상\s*구매", html)
    if m: print("FOUND:", m.group())
    else: print("없음")

    print("\n--- 가격 ---")
    m = re.search(r'"finalPrice"\s*:\s*"?([0-9,]+)"?', html)
    if m: print("finalPrice:", m.group(1))
    m2 = re.search(r'class="[^"]*price[^"]*"[^>]*>\s*([0-9,]+)', html)
    if m2: print("price element:", m2.group(1))

    print("\n--- 리뷰 ---")
    m = re.search(r'"reviewCount"\s*:\s*([0-9]+)', html)
    if m: print("reviewCount:", m.group(1))

    with open("C:/Users/KCW/scripts/debug_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 저장: {len(html):,} bytes")

finally:
    time.sleep(2)
    driver.quit()
