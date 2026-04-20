import re

html = open("C:/Users/KCW/scripts/debug_page.html", encoding="utf-8").read()

# ── 구매자 ──
m = re.search(r">([\s\d,]+명\s*이상)\s*</span>구매했어요", html)
print("buyers:", repr(m.group(1).strip()) if m else "NONE")

# ── 가격: HTML 원본 확인 ──
idx = html.find("finalPrice")
print("raw around finalPrice:", repr(html[idx:idx+50]))

# 여러 패턴 시도
for pat in [
    r'finalPrice\\":\\"([0-9,]+)\\"',
    r'"finalPrice":"([0-9,]+)"',
    r'"finalPrice":([0-9]+)',
    r'finalPrice\\\\\":\\\\\"([0-9,]+)\\\\\"',
]:
    m2 = re.search(pat, html)
    if m2:
        print(f"price [{pat[:30]}]:", m2.group(1))
        break
else:
    print("price: NONE")

# ── 리뷰 ──
idx2 = html.find("ratingCount")
print("raw around ratingCount:", repr(html[idx2:idx2+40]))

for pat in [
    r'ratingCount":"([0-9]+)"',
    r'ratingCount\\":\\"([0-9]+)\\"',
    r'"ratingCount":"([0-9]+)"',
]:
    m3 = re.search(pat, html)
    if m3:
        print(f"reviews [{pat[:30]}]:", m3.group(1))
        break
else:
    print("reviews: NONE")
