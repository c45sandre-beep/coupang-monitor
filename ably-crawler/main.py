"""
에이블리 파트너센터 모니터링
- 새 주문(발주 관리) 텔레그램 알림
- 미답변 문의 텔레그램 알림
- 실행할 때마다 신규 건만 알림
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

ABLY_EMAIL       = os.getenv("ABLY_EMAIL")
ABLY_PW          = os.getenv("ABLY_PW")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_WEB = "https://my.a-bly.com"
BASE_API = "https://api.a-bly.com"

SEEN_ORDERS    = Path(__file__).parent / "seen_orders.json"
SEEN_INQUIRIES = Path(__file__).parent / "seen_inquiries.json"
DEBUG_DIR      = Path(__file__).parent / "debug"


# ─────────────────────────────────────────
# 영속 저장
# ─────────────────────────────────────────

def load_seen(path: Path) -> set:
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")))
    return set()

def save_seen(path: Path, data: set) -> None:
    path.write_text(json.dumps(sorted(data), ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────
# 텔레그램
# ─────────────────────────────────────────

async def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        })
        r.raise_for_status()


# ─────────────────────────────────────────
# 로그인 → JWT 토큰 획득
# ─────────────────────────────────────────

async def get_jwt_token() -> str:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = await ctx.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        await page.goto(f"{BASE_WEB}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.fill('input[name="email"]', ABLY_EMAIL)
        await page.fill('input[name="password"]', ABLY_PW)
        await page.click('button:has-text("로그인")')
        await page.wait_for_url(f"{BASE_WEB}/dashboard", timeout=20_000)

        cookies = await ctx.cookies()
        await browser.close()

    for c in cookies:
        if c["name"] == "ably-seller-admin-jwt-token":
            return c["value"]

    DEBUG_DIR.mkdir(exist_ok=True)
    raise RuntimeError("JWT 토큰을 찾을 수 없습니다 — 로그인 실패 또는 쿠키명 변경")


# ─────────────────────────────────────────
# API 호출 헬퍼
# ─────────────────────────────────────────

def make_headers(token: str) -> dict:
    return {
        "Authorization": f"JWT {token}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": BASE_WEB,
    }


# ─────────────────────────────────────────
# 주문 조회 (발주 관리 - 배송 준비)
# ─────────────────────────────────────────

async def fetch_new_orders(token: str) -> list[dict]:
    """processing_status=1 : 결제 완료(배송 준비) 상태 주문 전체"""
    url = (
        f"{BASE_API}/seller/order_items/"
        "?processing_status[]=1&processing_sub_status[]=0"
        "&order=-checked_at"
        "&delivery_type[]=standard&delivery_type[]=today"
        "&delivery_type[]=combine&delivery_type[]=reserved"
        "&page=1&per_page=100&sponsorship_type=-1"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=make_headers(token))
        r.raise_for_status()
        data = r.json()

    orders = []
    for item in data.get("order_items", []):
        orders.append({
            "sno":        str(item.get("sno", "")),
            "order_sno":  str(item.get("order_sno", "")),
            "goods_name": item.get("goods_name", ""),
            "option":     item.get("option_title", ""),
            "qty":        item.get("ea", 1),
            "buyer":      item.get("buyer_name", ""),
            "paid_at":    item.get("checked_at", "")[:16] if item.get("checked_at") else "",
        })
    return orders


# ─────────────────────────────────────────
# 문의 조회 (미답변)
# ─────────────────────────────────────────

async def fetch_unanswered_inquiries(token: str) -> list[dict]:
    """status=1,2 : 미답변 문의 (최근 30일)"""
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    categories = (
        "category[]=2&category[]=101&category[]=120"
        "&category[]=3&category[]=102&category[]=121"
        "&category[]=4&category[]=103&category[]=122"
        "&category[]=5&category[]=104&category[]=123"
        "&category[]=9&category[]=11&category[]=106&category[]=125"
        "&category[]=12&category[]=107&category[]=126"
        "&category[]=13&category[]=108&category[]=127"
        "&category[]=14&category[]=109&category[]=128"
        "&category[]=15&category[]=110&category[]=129"
        "&category[]=16&category[]=111&category[]=130"
        "&category[]=19&category[]=153&category[]=172"
    )
    url = (
        f"{BASE_API}/seller/contact_rooms/"
        f"?start_date={start}&end_date={end}"
        "&order=-updated_latest_message_at"
        f"&{categories}"
        "&status[]=1&status[]=2"
        "&per_page=50"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=make_headers(token))
        r.raise_for_status()
        data = r.json()

    inquiries = []
    for room in data.get("contact_rooms", []):
        member    = room.get("member", {})
        last_msg  = room.get("latest_message", {})
        category  = room.get("category_name", "")
        inquiries.append({
            "sno":       str(room.get("sno", "")),
            "member":    member.get("name", ""),
            "category":  category,
            "message":   last_msg.get("content", "")[:60] if last_msg else "",
            "updated_at": room.get("updated_latest_message_at", "")[:16],
        })
    return inquiries


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────

async def main() -> None:
    missing = [k for k in ["ABLY_EMAIL","ABLY_PW","TELEGRAM_TOKEN","TELEGRAM_CHAT_ID"]
               if not os.getenv(k)]
    if missing:
        sys.exit(f"[!] .env 누락: {missing}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 에이블리 모니터링 시작")

    # JWT 토큰 획득
    print("[*] 로그인 중...")
    try:
        token = await get_jwt_token()
        print("[*] 로그인 성공")
    except Exception as e:
        await send_telegram(f"⚠️ <b>에이블리 로그인 실패</b>\n{e}")
        raise

    seen_orders    = load_seen(SEEN_ORDERS)
    seen_inquiries = load_seen(SEEN_INQUIRIES)

    errors = []

    # ── 주문 처리 ─────────────────────────────
    try:
        orders = await fetch_new_orders(token)
        print(f"[*] 발주 대기 {len(orders)}건 조회")
        new_orders = [o for o in orders if o["sno"] not in seen_orders]

        for o in new_orders:
            msg = (
                f"🛍 <b>에이블리 새 주문</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔢 주문번호: <code>{o['order_sno']}</code>\n"
                f"🏷 상품명:  {o['goods_name']}\n"
                f"🎨 옵션:    {o['option']}\n"
                f"📦 수량:    {o['qty']}개\n"
                f"👤 구매자:  {o['buyer']}\n"
                f"📅 결제일:  {o['paid_at']}"
            )
            await send_telegram(msg)
            seen_orders.add(o["sno"])

        if new_orders:
            save_seen(SEEN_ORDERS, seen_orders)
            print(f"[*] 신규 주문 {len(new_orders)}건 알림 전송")
        else:
            print("[*] 신규 주문 없음")

    except Exception as e:
        errors.append(f"주문 조회 오류: {e}")
        print(f"[!] 주문 오류: {e}")

    # ── 문의 처리 ─────────────────────────────
    try:
        inquiries = await fetch_unanswered_inquiries(token)
        print(f"[*] 미답변 문의 {len(inquiries)}건 조회")
        new_inqs = [i for i in inquiries if i["sno"] not in seen_inquiries]

        for inq in new_inqs:
            msg = (
                f"💬 <b>에이블리 미답변 문의</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔢 문의번호: <code>{inq['sno']}</code>\n"
                f"👤 고객:    {inq['member']}\n"
                f"📂 카테고리: {inq['category']}\n"
                f"💭 내용:    {inq['message']}\n"
                f"📅 시간:    {inq['updated_at']}\n"
                f"🔗 <a href='https://my.a-bly.com/inquiry'>답변하기</a>"
            )
            await send_telegram(msg)
            seen_inquiries.add(inq["sno"])

        if new_inqs:
            save_seen(SEEN_INQUIRIES, seen_inquiries)
            print(f"[*] 신규 문의 {len(new_inqs)}건 알림 전송")
        else:
            print("[*] 신규 미답변 문의 없음")

    except Exception as e:
        errors.append(f"문의 조회 오류: {e}")
        print(f"[!] 문의 오류: {e}")

    # ── 오류 알림 ─────────────────────────────
    if errors:
        await send_telegram(
            "⚠️ <b>에이블리 크롤러 오류</b>\n" + "\n".join(errors)
        )

    print("[완료]")


if __name__ == "__main__":
    asyncio.run(main())
