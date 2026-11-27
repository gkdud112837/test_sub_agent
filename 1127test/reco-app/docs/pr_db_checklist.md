# DB 변경 PR 본문 — data/schema-v1 (초안)

> SQL 실행과 merge는 사람이 한다. 이 PR은 파일만 바꾼다.

## ① 마이그레이션 SQL

| 순서 | 파일 | 대상 | 내용 |
|---|---|---|---|
| 1 | `supabase/schema.sql` | products · surveys · orders · place_order | 테이블 생성, 기본 권한 회수 → GRANT, RLS 켜기, products 읽기 정책, 주문 함수, 예시 상품 24행 |
| 2 | `supabase/policies.sql` | surveys · orders | 로그인 본인 행 읽기 정책 2개 |
| 3 | Table Editor → orders → Import CSV | orders | `data/instructor_orders.csv` 304행 (`source=instructor`, 가상) |

두 SQL 모두 다시 실행해도 안전합니다(`if not exists` · `drop policy if exists` · 비어 있을 때만 insert). 로컬 검증은 `npm run verify:sql`, 19개 항목 PASS입니다.

## ② RLS 정책 전후

| 테이블 | 역할 | 전 (테이블 없음) | 후 |
|---|---|---|---|
| products | anon · authenticated | — | SELECT 허용 (`using (true)`) · 쓰기 GRANT 없음 |
| surveys | anon | — | GRANT 없음 → 42501 |
| surveys | authenticated | — | SELECT 본인 행만 (`auth.uid() = user_id`) · 쓰기 없음 |
| orders | anon | — | GRANT 없음 → 42501 |
| orders | authenticated | — | SELECT 본인 행만 · 쓰기 없음 |
| 모든 테이블 쓰기 | service_role | — | 서버 함수 secret 키만 (RLS 우회) |
| place_order() | anon · authenticated | — | EXECUTE 회수 · service_role만 |

"누구나 쓰기" 정책은 없습니다. 공개 범위는 products 읽기 하나입니다.

## ③ 롤백

- `supabase/rollback.sql` 단계 A: 본인 행 정책 2개만 삭제합니다. 데이터 손실은 없고, 접근이 더 닫힌 상태가 됩니다.
- 단계 B: 함수와 테이블 3개를 삭제합니다. ⚠ **orders · surveys 데이터가 모두 사라집니다.** 실행 전에 CSV로 내보내야 합니다.
- 이전 Vercel 배포(v2, JSON 파일)는 DB를 읽지 않으므로, 롤백해도 옛 배포는 깨지지 않습니다.

## ④ 리뷰어 대시보드 확인 항목

- [ ] Table Editor: 세 테이블의 열 · 타입이 `docs/data_model.md`와 같은지, products 24행, orders 304행 이상
- [ ] Authentication → Policies: products 1개, surveys 1개, orders 1개, 세 테이블 모두 "RLS enabled"
- [ ] SQL Editor: `select count(*) from orders where source = 'instructor';` → 304
- [ ] publishable 키로 orders 조회 → `[]` 또는 42501 (spec S2 curl)
- [ ] Preview URL: 상품 목록 표시 → 추천 → 주문 → 새로고침 후 재고 감소 유지
