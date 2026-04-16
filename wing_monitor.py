"""
쿠팡 Wing 발주리스트 모니터링
- 매일 오전 9:10 실행
- 전날 대비 새 발주만 텔레그램 전송
- 실제 Chrome + CDP (봇 차단 우회)
"""

import os, re, sys, json, time, subprocess, requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# ── 경로 설정 ─────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
DATA_DIR     = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
ENV_FILE     = SCRIPT_DIR / ".env"

load_dotenv(ENV_FILE)

WING_ID      = os.getenv("WING_ID", "")
WING_PW      = os.getenv("WING_PW", "")
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
CHAT_ID      = os.getenv("CHAT_ID", "")

WING_URL     = "https://wing.coupang.com"
ORDER_PATH   = "/wing/vendor-inventory/po-list"   # 발주리스트 경로 (자동 탐색 fallback 있음)
CHROME_PATH  = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_PROFILE = r"C:\Users\KCW\AppData\Local\Google\Chrome\WingProfile"
DEBUG_PORT   = 9223  # coupang_monitor 와 포트 충돌 방지
# ─────────────────────────────────────────────────────


def send_telegram(message: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=15,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[텔레그램 오류] {e}", file=sys.stderr)
        return False


def data_file(date: datetime) -> Path:
    return DATA_DIR / f"wing_orders_{date.strftime('%Y-%m-%d')}.json"


def load_orders(date: datetime) -> list[dict]:
    f = data_file(date)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return []


def save_orders(date: datetime, orders: list[dict]):
    data_file(date).write_text(
        json.dumps(orders, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Chrome 실행 ───────────────────────────────────────

def launch_chrome() -> subprocess.Popen:
    return subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={CHROME_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1400,900",
        WING_URL,
    ])


def wait_chrome(timeout: int = 20) -> bool:
    for _ in range(timeout * 2):
        try:
            r = requests.get(f"http://localhost:{DEBUG_PORT}/json/version", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ── 로그인 ────────────────────────────────────────────

def is_logged_in(page) -> bool:
    """현재 페이지가 로그인된 상태인지 확인"""
    url = page.url
    return "login" not in url.lower() and "wing.coupang.com" in url


def do_login(page):
    """아이디/비밀번호 자동 입력 후 로그인"""
    print("  로그인 시도...")
    page.wait_for_load_state("domcontentloaded")

    # 아이디 필드
    for sel in ["#username", "#loginId", "input[name='username']",
                "input[name='loginId']", "input[type='text']"]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.fill(WING_ID)
                break
        except Exception:
            pass

    # 비밀번호 필드
    for sel in ["#password", "input[name='password']", "input[type='password']"]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.fill(WING_PW)
                break
        except Exception:
            pass

    # 로그인 버튼
    for sel in ["button[type='submit']", ".login-btn", "#loginBtn",
                "button:has-text('로그인')", "input[type='submit']"]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.click()
                break
        except Exception:
            pass

    # 로그인 완료 대기 (URL 변경)
    try:
        page.wait_for_url(lambda url: "login" not in url.lower(), timeout=15000)
        print("  로그인 성공!")
    except Exception:
        print("  로그인 대기 타임아웃 — 수동 확인 필요", file=sys.stderr)


# ── 발주리스트 페이지 이동 ─────────────────────────────

def navigate_to_order_list(page):
    """물류 > 발주리스트로 이동"""
    target_url = WING_URL + ORDER_PATH

    # 직접 URL로 시도
    page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(2000)

    # URL이 맞지 않으면 메뉴 클릭으로 탐색
    if ORDER_PATH not in page.url:
        print("  메뉴 탐색으로 이동 시도...")
        for menu_text in ["물류", "발주", "발주리스트", "Logistics", "Purchase Order"]:
            try:
                el = page.get_by_text(menu_text, exact=False).first
                if el.is_visible(timeout=2000):
                    el.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass

    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2000)
    print(f"  현재 URL: {page.url}")


# ── 발주 테이블 파싱 ──────────────────────────────────

def parse_order_table(page) -> list[dict]:
    """테이블에서 발주 데이터 추출 (페이지네이션 포함)"""
    all_orders = []
    page_num = 1

    while True:
        print(f"  페이지 {page_num} 파싱 중...")
        orders = extract_table_rows(page)
        if not orders:
            print(f"  페이지 {page_num}: 데이터 없음")
            break

        all_orders.extend(orders)

        # 다음 페이지 버튼
        next_btn = None
        for sel in ["button[aria-label='next']", ".pagination-next",
                    "button:has-text('다음')", "[class*=next]:not([disabled])"]:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1000) and el.is_enabled():
                    next_btn = el
                    break
            except Exception:
                pass

        if next_btn is None:
            break

        next_btn.click()
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1000)
        page_num += 1

        if page_num > 20:  # 안전 제한
            break

    return all_orders


def extract_table_rows(page) -> list[dict]:
    """테이블 행을 파싱해 발주 dict 목록 반환"""
    orders = []

    # 테이블 행 선택자 (여러 후보)
    for row_sel in ["table tbody tr", "[class*=table] [class*=row]",
                    "[class*=TableRow]", "tr[class*=order]"]:
        rows = page.locator(row_sel).all()
        if rows:
            for row in rows:
                try:
                    cells = row.locator("td").all()
                    if len(cells) < 3:
                        continue
                    texts = [c.inner_text().strip() for c in cells]
                    order = parse_cells(texts)
                    if order:
                        orders.append(order)
                except Exception:
                    pass
            if orders:
                break

    return orders


def parse_cells(texts: list[str]) -> dict | None:
    """셀 텍스트 목록에서 발주 정보 추출"""
    if not texts or len(texts) < 3:
        return None

    # 발주번호: 숫자만으로 된 긴 문자열 탐색
    order_no = ""
    status   = ""
    date_str = ""
    product  = ""
    qty      = ""
    amount   = ""

    for t in texts:
        t = t.strip()
        if not t:
            continue
        # 발주번호 패턴: 10자리 이상 숫자
        if re.match(r"^\d{8,}$", t) and not order_no:
            order_no = t
        # 날짜 패턴
        elif re.search(r"\d{4}[-./]\d{2}[-./]\d{2}", t) and not date_str:
            date_str = t
        # 상태 키워드
        elif any(k in t for k in ["접수", "확인", "완료", "취소", "처리", "대기",
                                   "ACCEPTED", "CONFIRMED", "COMPLETED"]) and not status:
            status = t
        # 금액 패턴: 숫자+원
        elif re.search(r"[0-9,]+\s*원", t) and not amount:
            amount = t
        # 수량 패턴: 숫자만 짧게
        elif re.match(r"^\d{1,5}$", t) and not qty:
            qty = t
        # 나머지는 제품명 후보
        elif len(t) > 5 and not product and not re.match(r"^[\d,.\s원]+$", t):
            product = t

    if not order_no:
        return None

    return {
        "order_no": order_no,
        "status":   status   or texts[1] if len(texts) > 1 else "",
        "date":     date_str or texts[2] if len(texts) > 2 else "",
        "product":  product  or texts[3] if len(texts) > 3 else "",
        "qty":      qty      or texts[4] if len(texts) > 4 else "",
        "amount":   amount   or texts[5] if len(texts) > 5 else "",
    }


# ── 텔레그램 메시지 포맷 ──────────────────────────────

def format_new_orders(new_orders: list[dict], today: str) -> str:
    if not new_orders:
        return f"✅ <b>Wing 발주 모니터링</b> ({today})\n새로운 발주가 없습니다."

    lines = [f"📦 <b>Wing 새 발주 알림</b> ({today})\n총 {len(new_orders)}건\n"]
    for o in new_orders:
        lines.append(
            f"━━━━━━━━━━━━━━\n"
            f"🔢 발주번호: <code>{o['order_no']}</code>\n"
            f"📌 상태: {o['status']}\n"
            f"🕐 일시: {o['date']}\n"
            f"📦 제품: {o['product']}\n"
            f"🔢 수량: {o['qty']}\n"
            f"💰 금액: {o['amount']}"
        )
    return "\n".join(lines)


# ── 메인 ─────────────────────────────────────────────

def main():
    now   = datetime.now()
    today = now.strftime("%Y-%m-%d %H:%M")
    print(f"[{today}] Wing 발주 모니터링 시작")

    if not WING_PW or WING_PW == "여기에_비밀번호_입력":
        msg = f"⚠️ Wing 모니터링 실패\n.env 파일에 WING_PW가 설정되지 않았습니다.\n{SCRIPT_DIR / '.env'}"
        send_telegram(msg)
        sys.exit(1)

    proc = launch_chrome()
    try:
        if not wait_chrome(timeout=20):
            raise RuntimeError("Chrome 실행 실패")

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            ctx = browser.contexts[0]

            # Wing 탭 찾기 또는 새로 열기
            page = next((pg for pg in ctx.pages if "wing.coupang.com" in pg.url), None)
            if page is None:
                page = ctx.new_page()
                page.goto(WING_URL, wait_until="domcontentloaded", timeout=20000)

            page.wait_for_timeout(3000)

            # 로그인 필요 여부 확인
            if not is_logged_in(page):
                do_login(page)
                page.wait_for_timeout(2000)

            # 발주리스트로 이동
            navigate_to_order_list(page)

            # 데이터 추출
            print("  발주 데이터 추출 중...")
            orders = parse_order_table(page)
            print(f"  추출된 발주: {len(orders)}건")

            if not orders:
                send_telegram(f"⚠️ Wing 발주 데이터를 가져오지 못했습니다.\n시각: {today}\nURL: {page.url}")
                return

        # 전날 데이터와 비교
        today_dt     = now.date()
        yesterday_dt = datetime.fromordinal(now.toordinal() - 1)
        prev_orders  = load_orders(yesterday_dt)
        prev_nos     = {o["order_no"] for o in prev_orders}

        new_orders = [o for o in orders if o["order_no"] not in prev_nos]
        print(f"  새 발주: {len(new_orders)}건 (전날: {len(prev_orders)}건)")

        # 오늘 데이터 저장
        save_orders(now, orders)

        # 텔레그램 전송
        msg = format_new_orders(new_orders, today)
        if send_telegram(msg):
            print(f"[{today}] 텔레그램 전송 완료")
        else:
            print(f"[{today}] 텔레그램 전송 실패", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        msg = f"⚠️ Wing 크롤링 오류\n시각: {today}\n{e}"
        send_telegram(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
