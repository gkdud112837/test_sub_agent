"""강사 제공 가상 주문 CSV를 대신 만드는 스크립트 (가상 데이터, seed 고정).

출력: data/instructor_orders.csv — Supabase Table Editor → orders → Import CSV
열: product_id, qty, ordered_at(UTC ISO), source
기간: 2026-10-01 ~ 2026-11-26 (한국 시간), 저녁·주말에 주문이 몰리게 만듦.
"""
import csv, random
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(1127)
KST = timezone(timedelta(hours=9))
N_PRODUCTS = 24                      # schema.sql 예시 상품 수 (id 1~24)
POPULAR = {1: 3, 2: 3, 10: 3, 11: 2, 19: 2, 22: 2, 23: 2}   # 가중치(가상)

rows = []
day = datetime(2026, 10, 1, tzinfo=KST)
end = datetime(2026, 11, 26, tzinfo=KST)
while day <= end:
    weekend = day.weekday() >= 5
    for _ in range(random.randint(6, 9) if weekend else random.randint(3, 6)):
        pid = random.choices(range(1, N_PRODUCTS + 1),
                             weights=[POPULAR.get(i, 1) for i in range(1, N_PRODUCTS + 1)])[0]
        hour = random.choices(range(7, 24), weights=[1,2,2,1,2,3,2,1,1,2,4,5,5,4,3,2,1])[0]
        # 23시대 주문은 UTC로 바꾸면 날짜가 바뀜 → AT TIME ZONE 검산 포인트
        ts = day.replace(hour=hour, minute=random.randint(0, 59))
        rows.append((pid, random.choice([1, 1, 1, 2, 2, 3]),
                     ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "instructor"))
    day += timedelta(days=1)

out = Path(__file__).resolve().parent.parent / "data" / "instructor_orders.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["product_id", "qty", "ordered_at", "source"])
    w.writerows(rows)
print(f"{len(rows)} rows -> {out}")
