# 법무사 보수 계산 (신탁부동산)

사용자가 신탁부동산 주소를 주며 "법무사 보수 계산"을 요청하면 `tools/registry-fee/fee.py`를 쓴다.

- 공시가격 조회 + 보수 계산: `python3 tools/registry-fee/fee.py lookup "주소" [--dong 101 --ho 1001]`
  - 여러 부동산을 한 신청서로 등기하면 주소를 여러 개 넘긴다 (과세표준액 합산 후 1회 계산).
- 금액만 있을 때: `python3 tools/registry-fee/fee.py calc 700000000`
- 필요 설정: 환경 변수 `VWORLD_API_KEY`(필수), `VWORLD_DOMAIN`(기본 http://localhost), 허용 도메인 `api.vworld.kr`.
- 보수표: 부동산등기 사건의 보수 Ⅰ-1 (소유권보존·이전·신탁 등) 기본보수. 부가세·누진·실비·공과금은 포함하지 않으니 답변에 그 점을 밝힌다.
- 과세표준액: 아파트 등 공동주택가격 → 개별주택가격 → 토지(개별공시지가×면적) 순. 일반 건물(상가 등) 시가표준액은 API로 안 나오므로 사용자에게 금액을 받는다.
- 답변에는 조회된 지번주소, 공시가격 종류·기준연도, 계산식을 함께 적는다.

vworld NED API 응답 필드명(pblntfPc, housePc, pblntfPclnd, lndpclAr)은 실제 호출로 아직 검증하지 않았다. 첫 조회 때 `--raw`로 원본을 확인하고, 다르면 스크립트를 고친다.
