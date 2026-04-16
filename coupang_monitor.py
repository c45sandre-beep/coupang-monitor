"""
쿠팡 제품 모니터링 스크립트
- 실제 Chrome을 headless 없이 원격 디버깅 포트로 실행
- Playwright가 그 Chrome에 연결해 DOM 읽기 (자동화 감지 우회)
"""

import re
import sys
import time
import subprocess
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ── 설정 ──────────────────────────────────────────────
BOT_TOKEN  = "8670485047:AAFst3egxBc3I1j9f3aFLpmT-3X5ODWfX-E"
CHAT_ID    = "8648861485"
PRODUCT_URL = (
    "https://www.coupang.com/vp/products/9470756373"
    "?itemId=28188833809&vendorItemId=95134341815"
)
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT  = 9222
# ─────────────────────────────────────────────────────


def send_telegram(message: str) -> bool:
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(api_url, json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"텔레그램 전송 오류: {e}", file=sys.stderr)
        return False


def launch_chrome() -> subprocess.Popen:
    """자동화 플래그 없는 일반 Chrome을 원격 디버깅 포트로 실행"""
    return subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        "--user-data-dir=C:\\Users\\KCW\\AppData\\Local\\Google\\Chrome\\CoupangProfile",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
        PRODUCT_URL,
    ])


def wait_for_chrome_ready(timeout: int = 15) -> bool:
    """Chrome 디버깅 포트가 열릴 때까지 대기"""
    for _ in range(timeout * 2):
        try:
            r = requests.get(f"http://localhost:{DEBUG_PORT}/json/version", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def crawl_coupang() -> dict:
    result = {"buyers": None, "price": None, "reviews": None}

    proc = launch_chrome()
    try:
        if not wait_for_chrome_ready(timeout=15):
            raise RuntimeError("Chrome 디버깅 포트 응답 없음")

        with sync_playwright() as p:
            # 이미 실행 중인 Chrome에 연결 (자동화 플래그 없음)
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            context = browser.contexts[0]

            # 제품 페이지 찾기 (이미 열려 있음)
            page = None
            for pg in context.pages:
                if "coupang.com" in pg.url:
                    page = pg
                    break
            if page is None:
                page = context.new_page()
                page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=30000)

            # 페이지 완전 로드 대기 (Akamai 챌린지 포함)
            deadline = time.time() + 20
            while time.time() < deadline:
                title = page.title()
                html  = page.content()
                if len(html) > 10000 and "Access Denied" not in title:
                    break
                time.sleep(1)
            else:
                raise RuntimeError(f"페이지 로드 실패: {page.title()}")

            html = page.content()

            # ── 구매자 수 ──
            # HTML: <span class="twc-text-[#D35200]"> 900명 이상 </span>구매했어요
            m = re.search(r">([\s\d,]+명\s*이상)\s*</span>구매했어요", html)
            if m:
                result["buyers"] = m.group(1).strip()

            # ── 가격 ──
            # JSON: finalPrice\":\"7,900\"  또는  finalPrice\":7900
            for pat in [
                r'finalPrice\\":\\"([0-9,]+)\\"',         # 이스케이프 JSON
                r'"finalPrice"\s*:\s*"([0-9,]+)"',        # 일반 JSON
                r'"finalPrice"\s*:\s*([0-9]+)',            # 숫자형
            ]:
                m = re.search(pat, html)
                if m:
                    raw = m.group(1).replace(",", "")
                    result["price"] = f"{int(raw):,}원"
                    break

            # ── 리뷰 ──
            # JSON: ratingCount":"119"  또는  ratingCount\":\"119\"
            for pat in [
                r'ratingCount"\s*:\s*"([0-9]+)"',
                r'ratingCount\\":\\"([0-9]+)\\"',
            ]:
                m = re.search(pat, html)
                if m:
                    result["reviews"] = m.group(1) + "개"
                    break

    finally:
        proc.terminate()

    return result


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{now}] 크롤링 시작...")

    try:
        data = crawl_coupang()
    except Exception as e:
        msg = f"⚠️ 쿠팡 크롤링 실패\n시각: {now}\n오류: {e}"
        send_telegram(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    buyers  = data["buyers"]  or "정보 없음"
    price   = data["price"]   or "정보 없음"
    reviews = data["reviews"] or "정보 없음"

    message = (
        f"📦 <b>쿠팡 제품 모니터링</b>\n"
        f"🕘 {now}\n\n"
        f"👥 한 달간 구매자: <b>{buyers}</b>\n"
        f"💰 현재 가격: <b>{price}</b>\n"
        f"⭐ 리뷰 개수: <b>{reviews}</b>\n\n"
        f'<a href="{PRODUCT_URL}">제품 페이지 바로가기</a>'
    )

    if send_telegram(message):
        print(f"[{now}] 텔레그램 전송 완료")
    else:
        print(f"[{now}] 텔레그램 전송 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
