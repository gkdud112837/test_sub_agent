-- =====================================================================
-- supabase/rollback.sql — 되돌리기 (DB 변경 PR 체크리스트 ③)
-- ⚠ 단계 B는 테이블과 데이터를 지운다. 실행 전에 Table Editor에서 orders를 CSV로 내보낼 것.
-- =====================================================================

-- 단계 A. policies.sql만 되돌리기 (데이터 손실 없음)
--   → 본인 행 조회 정책이 사라져 로그인 사용자도 orders·surveys를 못 읽게 됨(더 닫힌 상태)
drop policy if exists "본인 주문 조회" on public.orders;
drop policy if exists "본인 설문 조회" on public.surveys;

-- 단계 B. schema.sql 전체 되돌리기 (⚠ 데이터 손실: orders·surveys·products 전부)
--   필요할 때만 주석을 풀고 실행
-- drop function if exists public.place_order(bigint, integer, uuid, bigint);
-- drop table if exists public.orders;
-- drop table if exists public.surveys;
-- drop table if exists public.products;
