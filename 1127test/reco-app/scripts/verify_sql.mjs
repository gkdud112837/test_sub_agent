// scripts/verify_sql.mjs — Supabase에 올리기 전에 SQL을 로컬 Postgres(PGlite, WASM)로 실행해 보는 검증
// 실행: npm run verify:sql
// Supabase가 제공하는 것(anon·authenticated·service_role 역할, auth.users, auth.uid())은 흉내 내서 만든다.
// 실제 Supabase 검증(대시보드·publishable 키 조회)은 사람이 따로 한다 → docs/deploy_checklist.md
import { PGlite } from "@electric-sql/pglite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(root, p), "utf8");

const db = new PGlite();
let pass = 0, fail = 0;
const check = (name, ok, detail = "") => {
  ok ? pass++ : fail++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
};
async function asRole(role, sub, fn) {
  await db.exec(`reset role; select set_config('request.jwt.claim.sub', '${sub ?? ""}', false); set role ${role};`);
  try { return await fn(); } finally { await db.exec("reset role;"); }
}
async function expectError(name, role, sub, sql, codes) {
  try {
    const r = await asRole(role, sub, () => db.query(sql));
    check(name, false, `에러 없이 ${r.rows.length}행 반환`);
  } catch (e) {
    check(name, codes.includes(e.code), `code ${e.code} ${e.message}`);
  }
}

// ── 0. Supabase 흉내: 역할 · auth 스키마 ─────────────────────────────
await db.exec(`
  set timezone = 'UTC';
  create role anon nologin;
  create role authenticated nologin;
  create role service_role nologin bypassrls;
  create schema auth;
  create table auth.users (id uuid primary key);
  create function auth.uid() returns uuid language sql stable
    as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  grant usage on schema auth to anon, authenticated, service_role;
  grant execute on function auth.uid() to anon, authenticated, service_role;
  -- 가장 열린 프로젝트를 가정: 새 테이블·시퀀스에 anon·authenticated가 ALL을 받는 기본 권한 (review_v1 #2 재현)
  -- schema.sql의 revoke가 이걸 걷어 내야 아래 anon 테스트가 통과한다
  alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
  alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
`);
const A = "11111111-1111-1111-1111-111111111111";
const B = "22222222-2222-2222-2222-222222222222";
await db.exec(`insert into auth.users values ('${A}'), ('${B}');`);

// ── 1. schema.sql → policies.sql (두 번 실행해도 되는지 = 재실행 안전성) ──
for (let i = 0; i < 2; i++) {
  await db.exec(read("supabase/schema.sql"));
  await db.exec(read("supabase/policies.sql"));
}
const cnt = (await db.query("select count(*)::int n from products")).rows[0].n;
check("schema.sql 두 번 실행 후 products 24행(중복 없음)", cnt === 24, `${cnt}행`);

const rls = (await db.query(
  "select relname, relrowsecurity from pg_class where relname in ('products','surveys','orders') order by 1")).rows;
check("모든 테이블 RLS 켜짐", rls.length === 3 && rls.every((r) => r.relrowsecurity), JSON.stringify(rls));

// ── 2. 강사 제공 가상 주문 CSV 적재 (source = instructor) ──────────────
const lines = read("data/instructor_orders.csv").trim().split(/\r?\n/).slice(1);
for (const l of lines) {
  const [pid, qty, at, src] = l.split(",");
  await db.query("insert into orders (product_id, qty, ordered_at, source) values ($1,$2,$3,$4)", [+pid, +qty, at, src]);
}
check("instructor 주문 적재", lines.length >= 300, `${lines.length}행`);

// ── 3. 서버 함수 경로(service_role): 설문 → 주문 ───────────────────────
const sv = await asRole("service_role", "", () => db.query(
  `insert into surveys (user_id, household, categories, budget, cooking) values ($1,'1인','{채소}',5000,'간편') returning id`, [A]));
const surveyId = sv.rows[0].id;
const before = (await db.query("select stock from products where id = 2")).rows[0].stock;
await asRole("service_role", "", () => db.query("select place_order(2, 3, $1, $2)", [A, surveyId]));
await asRole("service_role", "", () => db.query("select place_order(1, 1, $1, null)", [B]));
await asRole("service_role", "", () => db.query("select place_order(1, 2, null, null)"));  // 비로그인 주문
const after = (await db.query("select stock from products where id = 2")).rows[0].stock;
check("place_order가 재고 차감", after === before - 3, `${before} → ${after}`);
try {
  await asRole("service_role", "", () => db.query("select place_order(6, 1)"));  // 재고 0 상품
  check("재고 0 상품 주문 거부", false);
} catch (e) { check("재고 0 상품 주문 거부", e.message.includes("OUT_OF_STOCK"), e.message); }
try {
  await asRole("service_role", "", () => db.query("select place_order(9999, 1)"));
  check("없는 상품 → NO_PRODUCT", false);
} catch (e) { check("없는 상품 → NO_PRODUCT", e.message.includes("NO_PRODUCT"), e.message); }
try {
  await asRole("service_role", "", () => db.query("select place_order(1, 21)"));
  check("수량 21 거부", false);
} catch (e) { check("수량 21 거부", e.message.includes("INVALID_QTY") || e.code === "23514", e.message); }

// ── 4. 보안 수용 기준: publishable 키(anon) ─────────────────────────────
const anonProducts = await asRole("anon", "", () => db.query("select id from products"));
check("anon: products 읽기 가능", anonProducts.rows.length === 24, `${anonProducts.rows.length}행`);
await expectError("anon: orders 조회 → 행 0개(42501 permission denied)", "anon", "", "select * from orders", ["42501"]);
await expectError("anon: surveys 조회 → 거부", "anon", "", "select * from surveys", ["42501"]);
await expectError("anon: orders insert 거부", "anon", "",
  "insert into orders (product_id, qty, source) values (1, 1, 'team')", ["42501"]);
await expectError("anon: products 재고 수정 거부", "anon", "", "update products set stock = 999", ["42501"]);
await expectError("anon: place_order 직접 호출 거부", "anon", "", "select place_order(1, 1)", ["42501"]);

// ── 5. 로그인 사용자(authenticated): 본인 행만 ───────────────────────
const aOrders = await asRole("authenticated", A, () => db.query("select user_id from orders"));
check("A: 본인 주문만 보임", aOrders.rows.length === 1 && aOrders.rows.every((r) => r.user_id === A), `${aOrders.rows.length}행`);
const bOrders = await asRole("authenticated", B, () => db.query("select user_id from orders"));
check("B: 본인 주문만 보임", bOrders.rows.length === 1 && bOrders.rows.every((r) => r.user_id === B), `${bOrders.rows.length}행`);
const bSurveys = await asRole("authenticated", B, () => db.query("select * from surveys"));
check("B: A의 설문 안 보임", bSurveys.rows.length === 0, `${bSurveys.rows.length}행`);
await expectError("authenticated: orders 직접 insert 거부", "authenticated", A,
  `insert into orders (product_id, qty, user_id, source) values (1, 1, '${A}', 'team')`, ["42501"]);
await expectError("authenticated: 남의 주문 user_id 바꾸기 거부", "authenticated", A,
  `update orders set user_id = '${A}'`, ["42501"]);

// ── 6. analysis/queries.sql 실행 ───────────────────────────────────────
const results = await db.exec(read("analysis/queries.sql"));
const titles = ["질문 1. 품목별 판매량 상위 5", "질문 2. 요일별 판매량(KST)", "질문 3. 재고 3 이하"];
results.filter((r) => r.fields.length).forEach((r, i) => {
  console.log(`\n[${titles[i]}]`);
  console.table(r.rows);
});
check("queries.sql 결과 3개", results.filter((r) => r.fields.length).length === 3);

console.log(`\n결과: PASS ${pass} · FAIL ${fail}`);
process.exit(fail ? 1 : 0);
