-- =====================================================================
-- supabase/schema.sql — 대구 오늘의 식재료 추천 v1
-- 기준 문서: docs/data_model.md
-- 실행: PR merge 뒤 사람이 Supabase SQL Editor에서 이 파일 → policies.sql 순서로 실행
-- 모든 예시 데이터는 가상입니다.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. 상품 테이블: 모두에게 같은 데이터. 재고(stock)가 0이면 추천에서 빠진다.
-- ---------------------------------------------------------------------
create table if not exists public.products (
  id          bigint generated always as identity primary key,           -- 기본키
  name        text    not null check (char_length(name) between 1 and 40),
  category    text    not null check (category in ('채소','과일','정육','수산','곡물','가공')),
  tags        text[]  not null default '{}',                               -- 추천 규칙·AI 사유의 유일한 근거
  portion     text    not null check (portion in ('1인','2~3인','4인+')),
  price       integer not null check (price >= 0),                          -- 원
  stock       integer not null check (stock >= 0),                          -- 재고 수량
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 2. 설문 테이블: 사람마다 다른 데이터. 비로그인이면 user_id = null.
-- ---------------------------------------------------------------------
create table if not exists public.surveys (
  id          bigint generated always as identity primary key,
  user_id     uuid references auth.users(id) on delete set null,            -- 외래키(로그인 시)
  household   text    not null check (household in ('1인','2~3인','4인+')),
  categories  text[]  not null check (
                cardinality(categories) between 1 and 3
                and categories <@ array['채소','과일','정육','수산','곡물','가공']::text[]),
  budget      integer not null check (budget in (5000, 10000, 30000)),
  cooking     text    not null check (cooking in ('간편','요리')),
  note        text    check (note is null or char_length(note) between 1 and 200),
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 3. 주문 테이블: 주문 로그. 상품 하나에 주문 여러 개(N:1).
--    ordered_at = 주문한 시각(분석용), created_at = DB에 들어간 시각.
-- ---------------------------------------------------------------------
create table if not exists public.orders (
  id          bigint generated always as identity primary key,
  product_id  bigint  not null references public.products(id),             -- 외래키
  qty         integer not null check (qty between 1 and 20),
  ordered_at  timestamptz not null default now(),
  user_id     uuid references auth.users(id) on delete set null,            -- 비로그인 주문은 null
  survey_id   bigint references public.surveys(id) on delete set null,
  source      text    not null check (source in ('instructor','team')),
  created_at  timestamptz not null default now()
);

-- 집계·본인 조회에 자주 쓰는 열에 인덱스
create index if not exists orders_product_id_idx on public.orders (product_id);
create index if not exists orders_ordered_at_idx on public.orders (ordered_at);
create index if not exists orders_user_id_idx    on public.orders (user_id);
create index if not exists surveys_user_id_idx   on public.surveys (user_id);

-- ---------------------------------------------------------------------
-- 4. GRANT: 테이블 자체에 들어오는 "문". (2026.5.30 이후 새 프로젝트는 빠뜨리면 42501)
--    anon          = products 읽기만
--    authenticated = products 읽기 + 본인 행 조회용 orders·surveys 읽기 (행 제한은 RLS가 함)
--    service_role  = 전체 (서버 함수의 secret 키)
-- ---------------------------------------------------------------------
-- 먼저 프로젝트 기본 권한을 걷어 낸다 (review_v1 #2 — 기본 권한이 anon에 ALL을 주는 프로젝트에서도
-- "anon = products select만"이 지켜지도록). 그다음 필요한 것만 다시 준다.
revoke all on public.products, public.surveys, public.orders from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
-- 앞으로 만들 테이블도 anon·authenticated가 자동으로 권한을 받지 않게 (review_v1 N3)
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;

grant usage on schema public to anon, authenticated, service_role;

grant select on public.products to anon, authenticated;
grant select on public.orders, public.surveys to authenticated;

grant all on public.products, public.surveys, public.orders to service_role;
grant usage, select on all sequences in schema public to service_role;

-- ---------------------------------------------------------------------
-- 5. RLS 켜기: 모든 테이블. 켜고 정책이 없으면 publishable 키로는 아무 행도 안 보인다.
--    products 읽기 정책 1개만 여기서 만들고, 나머지는 policies.sql(3교시)에서 추가.
-- ---------------------------------------------------------------------
alter table public.products enable row level security;
alter table public.surveys  enable row level security;
alter table public.orders   enable row level security;

-- products: 로그인 여부와 관계없이 읽기만 허용
drop policy if exists "누구나 상품 조회" on public.products;
create policy "누구나 상품 조회"
  on public.products for select
  to anon, authenticated
  using (true);

-- ---------------------------------------------------------------------
-- 6. 주문 함수: 재고 확인 → 차감 → 주문 기록을 한 번에(동시 주문에도 재고가 음수가 되지 않게).
--    service_role(서버 함수)만 실행할 수 있다. 브라우저에서 직접 부를 수 없다.
-- ---------------------------------------------------------------------
create or replace function public.place_order(
  p_product_id bigint,
  p_qty        integer,
  p_user_id    uuid    default null,
  p_survey_id  bigint  default null
) returns public.orders
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_order public.orders;
begin
  if p_qty is null or p_qty < 1 or p_qty > 20 then
    raise exception 'INVALID_QTY' using errcode = '22023';
  end if;

  -- 없는 상품은 재고 부족과 구분한다 (review_v1 #9)
  if not exists (select 1 from public.products where id = p_product_id) then
    raise exception 'NO_PRODUCT' using errcode = 'P0002';
  end if;

  -- 재고가 충분할 때만 차감 (조건부 update 한 문장이라 동시 주문에도 안전)
  update public.products
     set stock = stock - p_qty
   where id = p_product_id
     and stock >= p_qty;

  if not found then
    raise exception 'OUT_OF_STOCK' using errcode = 'P0001';
  end if;

  insert into public.orders (product_id, qty, user_id, survey_id, source)
  values (p_product_id, p_qty, p_user_id, p_survey_id, 'team')
  returning * into v_order;

  return v_order;
end;
$$;

revoke all on function public.place_order(bigint, integer, uuid, bigint) from public, anon, authenticated;
grant execute on function public.place_order(bigint, integer, uuid, bigint) to service_role;

-- ---------------------------------------------------------------------
-- 7. 예시 상품 24행 (가상 데이터). 다시 실행해도 중복되지 않게 비어 있을 때만 넣는다.
-- ---------------------------------------------------------------------
insert into public.products (name, category, tags, portion, price, stock)
select * from (values
  ('달성 토마토',         '채소', array['생식','샐러드'],     '2~3인', 4000, 12),
  ('달성 방울토마토',     '채소', array['생식','간식','간편'], '1인',   3500, 20),
  ('대구 미나리 한 단',   '채소', array['쌈','국물'],         '2~3인', 3000,  9),
  ('칠곡 애호박',         '채소', array['볶음','국물','요리'], '2~3인', 1800, 15),
  ('경산 샐러드 채소팩',  '채소', array['샐러드','간편'],     '1인',   3900,  3),
  ('군위 한우 국거리',    '정육', array['국물','요리'],       '2~3인', 9000,  0),
  ('군위 한우 불고기',    '정육', array['구이','요리'],       '4인+', 24000,  4),
  ('대구 막창 손질팩',    '정육', array['구이','간편'],       '2~3인', 12000, 6),
  ('한돈 앞다리 수육용',  '정육', array['수육','요리'],       '4인+', 15000,  2),
  ('닭가슴살 소포장',     '정육', array['간편','샐러드'],     '1인',   2900, 25),
  ('팔공산 사과',         '과일', array['생식','간식'],       '4인+',  5000,  7),
  ('청도 반시',           '과일', array['생식','간식'],       '2~3인', 6500,  1),
  ('경산 대추 한 봉',     '과일', array['간식','차'],         '1인',   4500, 10),
  ('성주 참외 2입',       '과일', array['생식','간식','간편'], '1인',   4800,  0),
  ('포항 손질 오징어',    '수산', array['볶음','요리'],       '2~3인', 8900,  5),
  ('동해 고등어 반손',    '수산', array['구이','간편'],       '2~3인', 6900,  8),
  ('영덕 홍게살 팩',      '수산', array['샐러드','간편'],     '1인',   9900,  3),
  ('바지락 해감팩',       '수산', array['국물','요리'],       '4인+',  7500, 11),
  ('달성 쌀 1kg',         '곡물', array['밥','요리'],         '4인+',  4900, 30),
  ('잡곡 혼합 소포장',    '곡물', array['밥','간편'],         '1인',   3200, 14),
  ('찰현미 500g',         '곡물', array['밥','요리'],         '2~3인', 3800,  6),
  ('대구 납작만두',       '가공', array['간식','구이','간편'], '2~3인', 5500, 18),
  ('국산콩 두부',         '가공', array['국물','구이','요리'], '2~3인', 2500, 22),
  ('경북 된장 소포장',    '가공', array['국물','요리'],       '1인',   4200,  9)
) as v(name, category, tags, portion, price, stock)
where not exists (select 1 from public.products);
