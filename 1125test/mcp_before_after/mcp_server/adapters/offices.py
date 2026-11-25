"""해외지사 어댑터 — offices.csv(가상 데이터)를 읽는다."""

import csv

from . import ROOT

CSV_PATH = ROOT / "offices.csv"


def fetch(country: str | None = None) -> dict:
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if country:
        matched = [r for r in rows if r["country"] == country]
        if not matched:
            available = ", ".join(r["country"] for r in rows)
            raise ValueError(f"해외지사가 없는 국가: {country} (지사 있는 국가: {available})")
        rows = matched
    return {"source": "offices_csv", "data": {"offices": rows}}
