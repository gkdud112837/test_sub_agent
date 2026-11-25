"""한국수출입은행 현재환율 API 어댑터 — 쉼표 · JPY(100) · result 코드 · 빈 날짜를 여기서 다 처리한다."""

import datetime
import os

import requests

URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
RESULT_CODES = {2: "DATA 코드 오류", 3: "인증코드 오류", 4: "일일 제한횟수 마감"}


def _latest_table() -> tuple[str, list[dict]]:
    """주말 · 공휴일 · 오전 11시 전에는 빈 목록이 오므로 최대 10일 거슬러 간다."""
    day = datetime.date.today()
    for _ in range(10):
        try:
            resp = requests.get(
                URL,
                params={
                    "authkey": os.environ["KOREAEXIM_AUTHKEY"],
                    "searchdate": day.strftime("%Y%m%d"),
                    "data": "AP01",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"환율 API 호출 실패 ({type(e).__name__})") from None
        rows = resp.json()
        if rows:
            code = rows[0].get("result")
            if code != 1:
                raise RuntimeError(f"환율 API 오류: {RESULT_CODES.get(code, code)}")
            return day.isoformat(), rows
        day -= datetime.timedelta(days=1)
    raise RuntimeError("최근 10일 동안 환율 데이터가 없습니다")


def _krw_per_unit(rows: list[dict], currency: str) -> float:
    if currency == "KRW":
        return 1.0
    for row in rows:
        unit = row["cur_unit"]  # 예: "USD", "JPY(100)"
        code, _, per = unit.partition("(")
        if code == currency:
            return float(row["deal_bas_r"].replace(",", "")) / int(per.rstrip(")") or 1)
    raise ValueError(f"지원하지 않는 통화: {currency}")


def fetch(base: str, target: str = "KRW") -> dict:
    base, target = base.upper(), target.upper()
    date, rows = _latest_table()
    rate = _krw_per_unit(rows, base) / _krw_per_unit(rows, target)
    return {"source": "koreaexim", "data": {"base": base, "target": target, "rate": round(rate, 4), "date": date}}
