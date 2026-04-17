"""
S2B 학교장터 발주 모니터링
- 2개 계정 순차 조회
- 매일 아침 전체 발주 요약을 텔레그램으로 전송
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

load_dotenv()

S2B_ACCOUNTS = [
    {"id": os.getenv("S2B_ID_1"), "pw": os.getenv("S2B_PW_1"), "label": os.getenv("S2B_ID_1", "계정1")},
    {"id": os.getenv("S2B_ID_2"), "pw": os.getenv("S2B_PW_2"), "label": os.getenv("S2B_ID_2", "계정2")},
]
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE      = "https://www.s2b.kr"
LOGIN_URL = f"{BASE}/S2BNCustomer/Login.do?type=sp"
ORDER_URL = f"{BASE}/S2BNVendor/proc100.do"

DEBUG_DIR = Path(__file__).parent / "debug"


# ───────────────────────────────────────────────
# 텔레그램
# ───────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        })
        r.raise_for_status()


# ───────────────────────────────────────────────
# 브라우저 헬퍼
# ───────────────────────────────────────────────

async def save_debug(page, label: str) -> None:
    DEBUG_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    await page.screenshot(path=str(DEBUG_DIR / f"{label}_{ts}.png"), full_page=False)


# ───────────────────────────────────────────────
# 로그인
# ───────────────────────────────────────────────

async def login(page, uid: str, pw: str) -> None:
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    uid_input = page.locator('form[name="vendor_loginForm"] input[name="uid"]')
    pwd_input = page.locator('form[name="vendor_loginForm"] input[name="pwd"]')

    await uid_input.fill(uid)
    await pwd_input.fill(pw)
    await page.wait_for_timeout(500)
    await page.evaluate("retrieveLogin2('vendor_loginForm', 3)")

    try:
        await page.wait_for_url("**/vendorMain.do", timeout=15_000)
    except PWTimeout:
        await save_debug(page, "login_fail")
        raise RuntimeError(f"로그인 실패 ({uid}) - debug/ 스크린샷 확인")


# ───────────────────────────────────────────────
# 발주 목록 조회
# ───────────────────────────────────────────────

async def fetch_orders(page) -> list[dict]:
    await page.goto(ORDER_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    orders = []

    # 계약번호 링크를 기준으로 행 파싱 (테이블 구조가 복잡해 링크로 찾음)
    rows = await page.query_selector_all("table tbody tr")

    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 5:
            continue

        texts = [((await c.text_content()) or "").strip() for c in cells]

        # 계약번호: 15자리 이상 숫자
        contract_no = texts[0].replace("\n", "").replace(" ", "")
        if not contract_no.isdigit() or len(contract_no) < 10:
            continue

        orders.append({
            "no":       contract_no,
            "name":     texts[1],
            "org":      texts[2],
            "amount":   texts[3],
            "status":   texts[4],
            "pay":      texts[7] if len(texts) > 7 else "",
            "date":     texts[8] if len(texts) > 8 else "",
        })

    return orders


# ───────────────────────────────────────────────
# 계정 1개 처리
# ───────────────────────────────────────────────

async def process_account(browser, account: dict) -> tuple[list, str]:
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
    label = account["label"]

    try:
        await login(page, account["id"], account["pw"])
        print(f"  [{label}] 로그인 성공")
        orders = await fetch_orders(page)
        print(f"  [{label}] 발주 {len(orders)}건 조회")
        return orders, None
    except Exception as e:
        print(f"  [{label}] 오류: {e}")
        return [], str(e)
    finally:
        await ctx.close()


# ───────────────────────────────────────────────
# 텔레그램 메시지 포맷
# ───────────────────────────────────────────────

STATUS_EMOJI = {
    "계약상대자결정": "📋",
    "배송준비":       "📦",
    "배송중":         "🚚",
    "검수중":         "🔍",
    "검수완료":       "✅",
    "결제대기":       "💳",
}

def build_summary(account_results: list[dict]) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    lines = [f"📊 <b>S2B 발주 현황 요약</b>", f"📅 {today}\n"]

    total_orders = 0
    total_amount = 0

    for result in account_results:
        label   = result["label"]
        orders  = result["orders"]
        error   = result["error"]

        lines.append(f"━━━━━━━━━━━━━━━")
        lines.append(f"👤 <b>{label}</b>")

        if error:
            lines.append(f"  ⚠️ 오류: {error}")
            continue

        if not orders:
            lines.append("  📭 진행중 발주 없음")
            continue

        # 상태별 그룹핑
        by_status: dict[str, list] = {}
        for o in orders:
            by_status.setdefault(o["status"], []).append(o)

        for status, items in by_status.items():
            emoji = STATUS_EMOJI.get(status, "🔹")
            lines.append(f"\n  {emoji} <b>{status}</b> ({len(items)}건)")
            for o in items:
                amt = o["amount"].replace(",", "")
                try:
                    total_amount += int(amt)
                except ValueError:
                    pass
                lines.append(
                    f"    • {o['name'][:20]}\n"
                    f"      {o['org']} | {o['amount']}원 | {o['date']}"
                )

        total_orders += len(orders)

    lines.append(f"\n━━━━━━━━━━━━━━━")
    lines.append(
        f"📦 전체 진행중 발주: <b>{total_orders}건</b>\n"
        f"💰 합계 금액: <b>{total_amount:,}원</b>"
    )
    return "\n".join(lines)


# ───────────────────────────────────────────────
# 메인
# ───────────────────────────────────────────────

async def main() -> None:
    missing = [k for k in ["S2B_ID_1","S2B_PW_1","S2B_ID_2","S2B_PW_2","TELEGRAM_TOKEN","TELEGRAM_CHAT_ID"]
               if not os.getenv(k)]
    if missing:
        sys.exit(f"[!] .env에 누락된 항목: {missing}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] S2B 발주 조회 시작")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )

        account_results = []
        for account in S2B_ACCOUNTS:
            orders, error = await process_account(browser, account)
            account_results.append({
                "label":  account["label"],
                "orders": orders,
                "error":  error,
            })

        await browser.close()

    summary = build_summary(account_results)
    await send_telegram(summary)
    print("[완료] 텔레그램 전송 완료")


if __name__ == "__main__":
    asyncio.run(main())
