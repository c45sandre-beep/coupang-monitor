import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

COUPANG_ID       = os.getenv("COUPANG_ID")
COUPANG_PW       = os.getenv("COUPANG_PW")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEEN_FILE  = Path(__file__).parent / "seen_orders.json"
DEBUG_DIR  = Path(__file__).parent / "debug"

VENDOR_URL        = "https://supplier.coupang.com"
LOGIN_URL         = f"{VENDOR_URL}/dashboard/KR"   # 미로그인 시 자동으로 Keycloak으로 리다이렉트
ORDER_URL         = f"{VENDOR_URL}/scm/purchase/order/list"


# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


async def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        })
        r.raise_for_status()


async def save_debug(page, label: str) -> None:
    """오류 발생 시 스크린샷 + HTML 저장"""
    DEBUG_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    await page.screenshot(path=str(DEBUG_DIR / f"{label}_{ts}.png"), full_page=True)
    (DEBUG_DIR / f"{label}_{ts}.html").write_text(await page.content(), encoding="utf-8")


# ──────────────────────────────────────────────
# 크롤러
# ──────────────────────────────────────────────

async def login(page) -> None:
    print("[*] 로그인 중...")
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # Keycloak SSO 폼 - JavaScript로 값 설정 (특수문자 안전)
    await page.wait_for_selector('input[name="username"]', timeout=15_000)

    def set_input_by_name(field_name: str, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("`", "\\`")
        return f"""
            (() => {{
                const el = document.querySelector('input[name="{field_name}"]');
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, `{escaped}`);
                el.dispatchEvent(new Event('input',  {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }})()
        """

    await page.evaluate(set_input_by_name("username", COUPANG_ID))
    await page.evaluate(set_input_by_name("password", COUPANG_PW))
    await page.wait_for_timeout(500)

    # 클릭 전 실제 입력값 확인
    pw_val = await page.evaluate("document.querySelector('input[name=\"password\"]').value")
    id_val = await page.evaluate("document.querySelector('input[name=\"username\"]').value")
    print(f"[디버그] username='{id_val}', password 길이={len(pw_val)}")
    await save_debug(page, "before_login")

    await page.click('input[type="submit"], button[type="submit"], #kc-login')

    try:
        await page.wait_for_url("https://supplier.coupang.com/**", timeout=20_000)
        print("[*] 로그인 성공")
    except PlaywrightTimeout:
        await save_debug(page, "login_fail")
        raise RuntimeError("로그인 실패 - debug/ 폴더의 스크린샷을 확인하세요")


async def fetch_orders(page) -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[*] 발주 목록 조회 (기준일: {today})")

    await page.goto(ORDER_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # ── 날짜 필터 설정 ──────────────────────────────
    # 포털마다 날짜 필터 UI가 다릅니다.
    # 아래는 대표적인 date-input 방식입니다. 동작하지 않으면 주석 처리 후
    # save_debug()로 HTML을 확인해 셀렉터를 교체하세요.
    await save_debug(page, "orders_page")

    # "오늘" 버튼으로 날짜 필터 설정
    try:
        await page.click('a:has-text("오늘"), button:has-text("오늘")', timeout=5000)
        await page.wait_for_timeout(1500)
        await page.click('button:has-text("검색"), input[value="검색"]', timeout=5000)
        await page.wait_for_timeout(2000)
    except Exception:
        print("[!] 날짜 필터 자동 설정 실패 - 전체 목록에서 오늘 날짜만 필터링합니다")

    # ── 테이블 파싱 ─────────────────────────────────
    # 컬럼: [0]체크박스 [1]발주번호 [2]발주유형 [3]주문유형 [4]발주상태
    #       [5]발주일시 [6]구분 [7]운송 [8]담당 [9]거래처명
    #       [10]상품명 [11]총SKU수 [12]납품센터(실) [13]납품센터
    #       [14]발주수량 [15]입고수량 [16]금액 [17]입고예약일
    orders = []
    rows = await page.query_selector_all("table.scmTable tbody tr")

    if not rows:
        await save_debug(page, "no_rows")
        print("[!] 테이블 행을 찾지 못했습니다 - debug/ 폴더 HTML을 확인하세요")
        return orders

    for row in rows:
        cells = await row.query_selector_all("td")
        texts = [((await c.text_content()) or "").strip() for c in cells]

        if len(texts) < 17:
            continue

        order_id   = re.sub(r'\s+', '', texts[1])
        order_date = texts[5]
        status     = texts[4]
        product    = texts[10]
        qty        = texts[14]
        amount     = texts[16]
        deadline   = texts[17]

        if not order_id:
            continue

        # 오늘 날짜 발주만
        if today not in order_date:
            continue

        orders.append({
            "id":       order_id,
            "date":     order_date,
            "status":   status,
            "product":  product,
            "qty":      qty,
            "amount":   amount,
            "deadline": deadline,
        })

    print(f"[*] 오늘 발주 {len(orders)}건 조회됨")
    return orders


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

async def main() -> None:
    if not all([COUPANG_ID, COUPANG_PW, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        sys.exit("[!] .env 파일에 COUPANG_ID / COUPANG_PW / TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 를 설정하세요")

    seen = load_seen()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        try:
            await login(page)
            orders = await fetch_orders(page)
        except Exception as e:
            await send_telegram(f"⚠️ <b>쿠팡 벤더 크롤링 오류</b>\n{e}")
            raise
        finally:
            await browser.close()

    # 신규 발주 필터
    new_orders = [o for o in orders if o["id"] not in seen]

    if not new_orders:
        print("[*] 새로운 발주 없음")
        return

    print(f"[*] 신규 발주 {len(new_orders)}건 → 텔레그램 전송")

    for o in new_orders:
        msg = (
            f"📦 <b>새 발주 도착</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🔢 발주번호: <code>{o['id']}</code>\n"
            f"📅 발주일시: {o['date']}\n"
            f"⏰ 납품기한: {o['deadline']}\n"
            f"🏷 상품명:  {o['product']}\n"
            f"📊 수량:    {o['qty']}\n"
            f"💰 금액:    {o['amount']}\n"
            f"📋 상태:    {o['status']}"
        )
        await send_telegram(msg)
        seen.add(o["id"])

    save_seen(seen)
    print("[*] 완료")


if __name__ == "__main__":
    asyncio.run(main())
