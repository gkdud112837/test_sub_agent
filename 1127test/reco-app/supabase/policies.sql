-- =====================================================================
-- supabase/policies.sql — 테이블별 RLS 정책 (3교시)
-- 전제: schema.sql을 먼저 실행 (RLS 켜기 · GRANT · products 읽기 정책 포함)
-- 기준: spec.md "보안" 절의 권한 표
--
-- | 테이블   | 읽기                              | 쓰기                                  |
-- |----------|-----------------------------------|---------------------------------------|
-- | products | 누구나 (anon, authenticated)      | 서버만 (secret 키, 정책 없음)          |
-- | surveys  | 로그인한 본인 행만 (authenticated) | 서버 함수만 추가, 수정·삭제 불가        |
-- | orders   | 로그인한 본인 행만 (authenticated) | 서버 함수(place_order)만 추가          |
--
-- anon에게는 surveys·orders 정책이 하나도 없다 → publishable 키로 조회하면 빈 결과(또는 42501).
-- insert/update/delete 정책도 하나도 없다 → 쓰기는 RLS를 건너뛰는 secret 키(서버)로만 가능.
-- =====================================================================

-- surveys: 로그인한 사용자는 자기 설문만 읽는다
drop policy if exists "본인 설문 조회" on public.surveys;
create policy "본인 설문 조회"
  on public.surveys for select
  to authenticated
  using ((select auth.uid()) = user_id);

-- orders: 로그인한 사용자는 자기 주문만 읽는다 (비로그인 주문 user_id=null은 누구에게도 안 보임)
drop policy if exists "본인 주문 조회" on public.orders;
create policy "본인 주문 조회"
  on public.orders for select
  to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------
-- 확인용 SELECT (SQL Editor는 관리자 권한이라 RLS가 적용되지 않음 → 정책 목록만 확인)
-- ---------------------------------------------------------------------
-- select tablename, policyname, roles, cmd from pg_policies where schemaname = 'public' order by 1, 2;
-- select relname, relrowsecurity from pg_class where relname in ('products','surveys','orders');
