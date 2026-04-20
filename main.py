"""
토스쇼핑 파트너센터 모니터링
- 새 주문(결제완료) 텔레그램 알림
- 미답변 고객문의 텔레그램 알림
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

TOSS_EMAIL       = os.getenv("TOSS_EMAIL")
TOSS_PW          = os.getenv("TOSS_PW")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_WEB     = "https://shopping-seller.toss.im"
API_ORDER    = "https://api-public.toss.im"
API_MERCHANT = "https://shopping-merchant-api.toss.im"
API_CHAT     = "https://biz-app-gateway.toss.im"

SEEN_ORDERS    = Path(__file__).parent / "seen_orders.json"
SEEN_INQUIRIES = Path(__file__).parent / "seen_inquiries.json"


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
# 로그인 -> TBIZAUTH 쿠키 + merchantId 획득
# ─────────────────────────────────────────

async def get_auth_info() -> tuple[str, int]:
    """(tbizauth_token, merchant_id) 반환"""
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
        await page.fill('input[name="username"]', TOSS_EMAIL)
        await page.fill('input[name="password"]', TOSS_PW)
        await page.click('button[type="submit"]')
        await page.wait_for_url(f"{BASE_WEB}/**", timeout=20_000)
        await page.wait_for_timeout(3000)

        if "login" in page.url:
            await browser.close()
            raise RuntimeError("로그인 실패 - URL이 여전히 login 페이지")

        cookies = await ctx.cookies()

        # merchantId는 localStorage에서 가져옴
        ls_raw = await page.evaluate("localStorage.getItem('@shopping-seller/currentMerchant_2023-11-01')")
        merchant_id = 0
        if ls_raw:
            try:
                merchant_id = json.loads(ls_raw).get("merchantId", 0)
            except Exception:
                pass

        await browser.close()

    tbizauth = ""
    for c in cookies:
        if c["name"] == "TBIZAUTH":
            tbizauth = c["value"]
            break

    if not tbizauth:
        raise RuntimeError("TBIZAUTH 쿠키를 찾을 수 없습니다 - 로그인 실패")
    if not merchant_id:
        raise RuntimeError("merchantId를 가져올 수 없습니다")

    return tbizauth, merchant_id


# ─────────────────────────────────────────
# API 헤더
# ─────────────────────────────────────────

def make_headers(token: str, merchant_id: int) -> dict:
    return {
        "Cookie": f"TBIZAUTH={token}",
        "x-merchant-id": str(merchant_id),
        "x-toss-frontend-service": "shopping-seller-toss-im",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": BASE_WEB,
    }


# ─────────────────────────────────────────
# 광고비 잔액 조회
# ─────────────────────────────────────────

async def fetch_ad_balance(token: str, merchant_id: int) -> dict:
    """광고비 지갑 잔액"""
    url = f"{API_MERCHANT}/api-public/v3/shopping-ads/merchant/info/wallet"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=make_headers(token, merchant_id))
        r.raise_for_status()
        data = r.json()
    wallet = data.get("success", {}).get("wallet", {})
    return {
        "paid":  wallet.get("paidMoneyAmount", 0),
        "free":  wallet.get("freeMoneyAmount", 0),
        "total": wallet.get("totalAmount", 0),
    }


# ─────────────────────────────────────────
# 주문 조회 (결제완료 - 신규 주문)
# ─────────────────────────────────────────

async def fetch_new_orders(token: str, merchant_id: int) -> list[dict]:
    """결제완료 상태 주문 (최근 7일)"""
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    url = f"{API_ORDER}/api-public/v3/shopping-order/order/histories"
    body = {
        "pageType": "ORDER_MANAGEMENT",
        "orderSearchStatus": "결제완료",
        "merchantId": merchant_id,
        "masking": False,
        "startDate": start,
        "endDate": end,
        "queryType": "ORDER_ID",
        "query": "",
        "pageSize": 200,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=body, headers=make_headers(token, merchant_id))
        r.raise_for_status()
        data = r.json()

    orders = []
    for item in data.get("success", {}).get("results", []):
        orders.append({
            "order_product_id": str(item.get("orderProductId", "")),
            "order_id":         str(item.get("orderId", "")),
            "product_name":     item.get("productName", ""),
            "option":           item.get("optionName", ""),
            "qty":              item.get("quantity", 1),
            "buyer":            item.get("ordererName", ""),
            "status":           item.get("orderProductStatus", ""),
            "deadline":         item.get("shippingDeadlineAt", ""),
        })
    return orders


# ─────────────────────────────────────────
# 문의 조회 (미답변 고객 채팅)
# ─────────────────────────────────────────

async def fetch_unanswered_inquiries(token: str, merchant_id: int) -> list[dict]:
    """미답변 고객 문의 채팅방"""
    url = f"{API_CHAT}/business-chat/domain-group/rooms?filter=UNANSWERED&size=50&page=0"

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=make_headers(token, merchant_id))
        r.raise_for_status()
        data = r.json()

    inquiries = []
    for room in data.get("success", {}).get("rooms", []):
        last_msg = room.get("lastMessage", {}) or {}
        receiver = room.get("receiver", {}) or {}
        inquiries.append({
            "room_id":   str(room.get("roomId", "")),
            "customer":  receiver.get("name", ""),
            "message":   last_msg.get("content", "")[:80] if last_msg else "",
            "sent_at":   (last_msg.get("sentAt", "") or "")[:16],
            "unread":    room.get("unreadCount", 0),
        })
    return inquiries


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────

async def main() -> None:
    missing = [k for k in ["TOSS_EMAIL", "TOSS_PW", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
               if not os.getenv(k)]
    if missing:
        sys.exit(f"[!] .env 누락: {missing}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 토스쇼핑 모니터링 시작")

    # 인증 정보 획득
    print("[*] 로그인 중...")
    try:
        token, merchant_id = await get_auth_info()
        print(f"[*] 로그인 성공 (merchantId: {merchant_id})")
    except Exception as e:
        await send_telegram(f"<b>토스쇼핑 로그인 실패</b>\n{e}")
        raise

    seen_orders    = load_seen(SEEN_ORDERS)
    seen_inquiries = load_seen(SEEN_INQUIRIES)
    errors = []

    # ── 주문 처리 ─────────────────────────────
    try:
        orders = await fetch_new_orders(token, merchant_id)
        print(f"[*] 결제완료 주문 {len(orders)}건 조회")
        new_orders = [o for o in orders if o["order_product_id"] not in seen_orders]

        for o in new_orders:
            msg = (
                f"🛍 <b>토스쇼핑 새 주문</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔢 주문번호: <code>{o['order_id']}</code>\n"
                f"🏷 상품명:  {o['product_name']}\n"
                f"🎨 옵션:    {o['option']}\n"
                f"📦 수량:    {o['qty']}개\n"
                f"👤 구매자:  {o['buyer']}\n"
                f"📅 발송기한: {o['deadline']}\n"
                f"🔗 <a href='https://shopping-seller.toss.im/orders/order-management'>주문관리</a>"
            )
            await send_telegram(msg)
            seen_orders.add(o["order_product_id"])

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
        inquiries = await fetch_unanswered_inquiries(token, merchant_id)
        print(f"[*] 미답변 문의 {len(inquiries)}건 조회")
        new_inqs = [i for i in inquiries if i["room_id"] not in seen_inquiries]

        for inq in new_inqs:
            msg = (
                f"💬 <b>토스쇼핑 미답변 문의</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"👤 고객:   {inq['customer']}\n"
                f"💭 내용:   {inq['message']}\n"
                f"🔔 미읽음: {inq['unread']}건\n"
                f"📅 시간:   {inq['sent_at']}\n"
                f"🔗 <a href='https://shopping-seller.toss.im/customer-support'>답변하기</a>"
            )
            await send_telegram(msg)
            seen_inquiries.add(inq["room_id"])

        if new_inqs:
            save_seen(SEEN_INQUIRIES, seen_inquiries)
            print(f"[*] 신규 문의 {len(new_inqs)}건 알림 전송")
        else:
            print("[*] 신규 미답변 문의 없음")

    except Exception as e:
        errors.append(f"문의 조회 오류: {e}")
        print(f"[!] 문의 오류: {e}")

    # ── 광고비 잔액 확인 ─────────────────────────
    try:
        balance = await fetch_ad_balance(token, merchant_id)
        total = balance["total"]
        print(f"[*] 광고비 잔액: {total:,}원 (충전금 {balance['paid']:,} + 무료 {balance['free']:,})")
        # 5만원 미만이면 텔레그램 알림
        if total < 50_000:
            await send_telegram(
                f"💸 <b>토스쇼핑 광고비 잔액 부족</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"현재 잔액: <b>{total:,}원</b>\n"
                f"  - 충전금: {balance['paid']:,}원\n"
                f"  - 무료금: {balance['free']:,}원\n"
                f"🔗 <a href='https://shopping-seller.toss.im/ads'>광고 충전</a>"
            )
    except Exception as e:
        errors.append(f"광고비 잔액 오류: {e}")
        print(f"[!] 광고비 잔액 오류: {e}")

    # ── 오류 알림 ─────────────────────────────
    if errors:
        await send_telegram(
            "<b>토스쇼핑 크롤러 오류</b>\n" + "\n".join(errors)
        )

    print("[완료]")


if __name__ == "__main__":
    asyncio.run(main())
