#!/usr/bin/env python3
"""신탁부동산 공시가격 조회 + 법무사 기본보수(부동산등기 소유권보존·이전·신탁 등) 계산.

사용법
  python3 fee.py calc 700000000 [금액 ...]            # 과세표준액(원)으로 보수만 계산 (여러 개면 합산)
  python3 fee.py lookup "주소" [--dong 101] [--ho 1001] [--year 2026] [--raw]
  python3 fee.py lookup "주소1" "주소2" ...            # 여러 부동산을 1건 신청 → 과세표준액 합산

환경 변수
  VWORLD_API_KEY  vworld 오픈API 인증키 (필수, lookup)
  VWORLD_DOMAIN   인증키 발급 시 등록한 서비스URL (기본 http://localhost)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

# (구간 상한, 구간 하한, 하한에서의 보수, 초과액에 곱하는 요율)
FEE_TABLE = [
    (50_000_000, 0, 210_000, 0),
    (100_000_000, 50_000_000, 210_000, 10 / 10_000),
    (300_000_000, 100_000_000, 260_000, 9 / 10_000),
    (500_000_000, 300_000_000, 440_000, 8 / 10_000),
    (1_000_000_000, 500_000_000, 600_000, 7 / 10_000),
    (2_000_000_000, 1_000_000_000, 950_000, 5 / 10_000),
    (20_000_000_000, 2_000_000_000, 1_450_000, 4 / 10_000),
    (float("inf"), 20_000_000_000, 8_650_000, 1 / 10_000),
]


def base_fee(amount):
    """과세표준액(원) → 기본보수(원, 원 단위 미만 버림)."""
    for upper, lower, fixed, rate in FEE_TABLE:
        if amount <= upper:
            return int(fixed + max(amount - lower, 0) * rate), (lower, fixed, rate)
    raise ValueError(amount)


def explain(amount):
    fee, (lower, fixed, rate) = base_fee(amount)
    if rate == 0:
        return fee, f"{amount:,}원 ≤ 5천만원 → {fee:,}원"
    return fee, (f"{fixed:,} + ({amount:,} − {lower:,}) × {round(rate * 10_000)}/10,000"
                 f" = {fee:,}원")


# ---------------------------------------------------------------- vworld

API = "https://api.vworld.kr"


def _key():
    key = os.environ.get("VWORLD_API_KEY")
    if not key:
        sys.exit("VWORLD_API_KEY 환경 변수가 없습니다. 클라우드 환경 설정 → 환경 변수에 등록 후 새 세션에서 실행하세요.")
    return key


def _get(path, params):
    params = dict(params, key=_key(), domain=os.environ.get("VWORLD_DOMAIN", "http://localhost"))
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def search_parcel(address):
    """주소(지번 또는 도로명) → [(pnu, 지번주소)]."""
    def search(query, category):
        data = _get("/req/search", {
            "service": "search", "request": "search", "version": "2.0", "size": 10, "page": 1,
            "query": query, "type": "address", "category": category,
            "format": "json", "errorformat": "json",
        })
        return ((data.get("response") or {}).get("result") or {}).get("items") or []

    items = search(address, "parcel")
    if items:
        return [(it["id"], it["address"].get("parcel")) for it in items]
    # 도로명주소 → 지번주소로 바꿔 다시 검색
    out = []
    for it in search(address, "road"):
        parcel = (it.get("address") or {}).get("parcel")
        if parcel:
            out += [(p["id"], p["address"].get("parcel")) for p in search(parcel, "parcel")]
    return out


def _rows(data):
    """NED 응답 {"xxxs": {"field": [...]}} 에서 행 목록 꺼내기."""
    for v in data.values():
        if isinstance(v, dict) and "field" in v:
            f = v["field"]
            return f if isinstance(f, list) else [f]
    return []


def ned(name, pnu, year, **extra):
    params = {"pnu": pnu, "format": "json", "numOfRows": 1000, "pageNo": 1, **extra}
    if year:
        params["stdrYear"] = year
    return _rows(_get(f"/ned/data/{name}", params))


def _num(s):
    return re.sub(r"\D", "", str(s or ""))


def _latest(rows, year_key="stdrYear"):
    if not rows:
        return []
    top = max(str(r.get(year_key, "")) for r in rows)
    return [r for r in rows if str(r.get(year_key, "")) == top]


def lookup(pnu, dong, ho, year, raw):
    """pnu → (과세표준액, 설명). 공동주택 → 개별주택 → 토지(공시지가×면적) 순으로 시도."""
    years = [year] if year else [None]

    for y in years:
        rows = ned("getApartHousingPriceAttr", pnu, y)
        if raw:
            print(json.dumps(rows[:5], ensure_ascii=False, indent=1))
        rows = _latest(rows)
        if rows:
            if dong:
                rows = [r for r in rows if _num(r.get("dongNm")) == _num(dong)] or rows
            if ho:
                rows = [r for r in rows if _num(r.get("hoNm")) == _num(ho)]
            if len(rows) == 1:
                r = rows[0]
                price = int(_num(r.get("pblntfPc")))
                return price, f"공동주택가격 {r.get('stdrYear')}년 {r.get('dongNm')}동 {r.get('hoNm')}호 {price:,}원"
            if not ho:
                return None, f"공동주택입니다. 동·호를 지정하세요 (--dong, --ho). 후보 {len(rows)}건"
            return None, "해당 동·호의 공동주택가격을 찾지 못했습니다"

    for y in years:
        rows = _latest(ned("getIndvdHousingPriceAttr", pnu, y))
        if raw:
            print(json.dumps(rows[:5], ensure_ascii=False, indent=1))
        if rows:
            r = rows[0]
            price = int(_num(r.get("housePc")))
            return price, f"개별주택가격 {r.get('stdrYear')}년 {price:,}원 (토지+건물)"

    for y in years:
        rows = _latest(ned("getLandCharacteristics", pnu, y))
        if raw:
            print(json.dumps(rows[:5], ensure_ascii=False, indent=1))
        if rows:
            r = rows[0]
            unit = int(_num(r.get("pblntfPclnd")))
            area = float(r.get("lndpclAr") or 0)
            price = int(unit * area)
            return price, (f"개별공시지가 {r.get('stdrYear')}년 {unit:,}원/㎡ × {area:,}㎡ = {price:,}원"
                           " (토지만. 지상 건물이 있으면 건물 시가표준액 별도 필요)")

    return None, "공시가격 자료를 찾지 못했습니다"


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calc")
    c.add_argument("amounts", nargs="+", type=lambda s: int(s.replace(",", "")))
    l = sub.add_parser("lookup")
    l.add_argument("addresses", nargs="+")
    l.add_argument("--dong")
    l.add_argument("--ho")
    l.add_argument("--year", type=int)
    l.add_argument("--raw", action="store_true", help="API 원본 응답 일부 출력")
    a = ap.parse_args()

    if a.cmd == "calc":
        total = sum(a.amounts)
    else:
        total = 0
        for addr in a.addresses:
            hits = search_parcel(addr)
            if not hits:
                sys.exit(f"[{addr}] 주소 검색 결과가 없습니다")
            pnu, parcel = hits[0]
            print(f"[{addr}] → {parcel} (PNU {pnu})" + (f"  ※ 후보 {len(hits)}건 중 첫 번째" if len(hits) > 1 else ""))
            price, note = lookup(pnu, a.dong, a.ho, a.year, a.raw)
            print("  " + note)
            if price is None:
                sys.exit(1)
            total += price

    fee, how = explain(total)
    print(f"\n과세표준액 합계: {total:,}원")
    print(f"기본보수: {how}")
    print("※ 기본보수만 계산. 부가세·누진/실비·공과금(등록면허세 등) 미포함")


if __name__ == "__main__":
    main()
