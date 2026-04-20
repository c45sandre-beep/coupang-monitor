import sys, re, time, subprocess, requests
from playwright.sync_api import sync_playwright

PRODUCT_URL = "https://www.coupang.com/vp/products/9470756373?itemId=28188833809&vendorItemId=95134341815"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT  = 9222

proc = subprocess.Popen([
    CHROME_PATH,
    f"--remote-debugging-port={DEBUG_PORT}",
    r"--user-data-dir=C:\Users\KCW\AppData\Local\Google\Chrome\CoupangProfile",
    "--no-first-run", "--no-default-browser-check",
    PRODUCT_URL,
])

for _ in range(30):
    try:
        r = requests.get(f"http://localhost:{DEBUG_PORT}/json/version", timeout=1)
        if r.status_code == 200: break
    except: pass
    time.sleep(0.5)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
    context = browser.contexts[0]
    page = None
    for pg in context.pages:
        if "coupang" in pg.url:
            page = pg
            break
    if page is None:
        page = context.new_page()
        page.goto(PRODUCT_URL)

    for _ in range(20):
        html = page.content()
        if len(html) > 10000 and "Access Denied" not in page.title(): break
        time.sleep(1)

    html = page.content()
    print(f"HTML size: {len(html):,} / title: {page.title()}")

    print("\n=== 구매자 패턴 ===")
    for m in re.findall(r".{0,20}구매.{0,20}", html)[:10]:
        print(repr(m))

    print("\n=== 가격 패턴 ===")
    for m in re.findall(r".{0,10}[0-9,]{4,}.{0,10}원.{0,10}", html)[:10]:
        print(repr(m))

    print("\n=== 119 주변 ===")
    for m in re.findall(r".{0,20}119.{0,20}", html)[:5]:
        print(repr(m))

    with open("C:/Users/KCW/scripts/debug_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\nHTML 저장 완료")

proc.terminate()
