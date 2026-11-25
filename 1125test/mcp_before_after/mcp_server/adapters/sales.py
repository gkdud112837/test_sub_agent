"""sales.db 어댑터 — SQL은 여기에만 있다."""

import sqlite3

from . import ROOT

DB_PATH = ROOT / "sales.db"


def fetch(country: str | None = None) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        if country:
            rows = conn.execute(
                "SELECT country, amount, currency FROM sales WHERE country = ?", (country,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT country, amount, currency FROM sales").fetchall()
    return {
        "source": "sales_db",
        "data": {"sales": [{"country": c, "amount": a, "currency": cur} for c, a, cur in rows]},
    }
