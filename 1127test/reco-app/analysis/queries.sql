-- =====================================================================
-- analysis/queries.sql — SQL 집계 쿼리 3개 (데이터·서비스 트랙)
-- 기준: supabase/schema.sql · 실행: Supabase SQL Editor (관리자 권한, RLS 미적용 → SELECT만)
--
-- 질문 1. 품목별 판매량 합계 상위 5개는? (orders JOIN products)
-- 질문 2. 요일별 판매량 합계는? (한국 시간 기준, 1=월 … 7=일)
-- 질문 3. 재고(stock)가 3 이하인 품목은? (재고 0 포함 → 보충 대상)
-- =====================================================================


-- 질문 1. 품목별 판매량 합계 상위 5개
--   FROM·JOIN : 주문 행마다 product_id로 상품 이름을 붙인다 (외래키 → 기본키)
--   WHERE     : 수량이 0보다 큰 주문만 (schema가 1~20으로 막지만 반품 행이 생길 때를 대비)
--   GROUP BY  : 상품별로 묶어 SUM(qty)
--   ORDER BY·LIMIT : 합계가 큰 순서로 5개, 동점이면 id 순
SELECT p.id,
       p.name,
       SUM(o.qty)  AS total_qty,
       COUNT(*)    AS order_count
FROM orders o
JOIN products p ON p.id = o.product_id
WHERE o.qty > 0
GROUP BY p.id, p.name
ORDER BY total_qty DESC, p.id
LIMIT 5;


-- 질문 2. 요일별 판매량 합계 (한국 시간)
--   AT TIME ZONE 'Asia/Seoul' : UTC로 저장된 ordered_at을 한국 시각으로 바꾼 뒤 요일을 뽑는다
--                               (빼면 한국 시간 0~9시 주문이 전날 요일로 집계됨)
--   GROUP BY : 요일(ISODOW) 값끼리 묶어 SUM(qty)
SELECT EXTRACT(ISODOW FROM o.ordered_at AT TIME ZONE 'Asia/Seoul') AS dow,
       SUM(o.qty) AS total_qty,
       COUNT(*)   AS order_count
FROM orders o
GROUP BY dow
ORDER BY dow;


-- 질문 3. 재고 3 이하 품목 목록
--   WHERE    : stock <= 3 인 행만 남긴다 (JOIN·GROUP BY 없음)
--   ORDER BY : 재고가 적은 것부터 → 보충 우선순위
SELECT id, name, category, stock
FROM products
WHERE stock <= 3
ORDER BY stock, id;
