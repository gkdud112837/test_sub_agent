# 배포 전 점검표 — 웹서비스 v1

## A. 로컬에서 끝낸 것 (2026-11-27, Claude Code)

- [x] `npm run build` 통과 (Next.js 16.4, proxy 포함)
- [x] `npm run verify:sql` PASS 19 / FAIL 0 (PGlite: schema · policies · RLS · place_order · queries.sql)
- [x] `node scripts/test_redirect.ts` PASS 9 (오픈 리다이렉트 회귀)
- [x] 빌드 산출물 `.next/static`에 `SUPABASE_SECRET_KEY` · `GEMINI_API_KEY` · Gemini 주소 없음
- [x] 키 없이 실행: 화면은 "환경변수가 설정되지 않았어요", API는 일반 오류 문구(내부 정보 없음)
- [x] 입력 검증(잘못된 선택지 · 201자 메모 · 중복 분류 · 수량 21 · JSON 아님 · text/plain · 다른 Origin) → 400/415
- [x] 레이트 리밋: 비로그인 주문 6번째부터 429
- [x] `docs/review_v1.md` 높음 0개, 중간 5개 수정

## B. 사람이 할 것 (계정 · 키가 필요해 Claude가 할 수 없음)

1. **Supabase**: 팀 조직에서 New project(리전 서울) 생성, 팀원 초대
2. **SQL 실행**: SQL Editor에서 `schema.sql` → `policies.sql` 순서로 실행. Table Editor → orders → Import `data/instructor_orders.csv`
3. **Auth**: Authentication → URL Configuration
   - Site URL = 배포 URL
   - Redirect URLs에 `https://<배포>/auth/callback`, `http://localhost:3000/auth/callback` 추가
4. **키**: 각자 Settings → API Keys에서 복사해 `.env.local`에 넣음. Google AI Studio에서 `GEMINI_API_KEY` 발급. 키 값은 채팅에 붙여 넣지 않음
5. **Vercel 환경변수** (Production · Preview 둘 다, 이름만 비교):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
   - `SUPABASE_SECRET_KEY`
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL` (선택)
   - 입력한 뒤 **재배포**
6. **Git**: `git ls-files | grep -i env` → `.env.example`만 나와야 함

## C. 배포 URL에서 사람이 확인할 수용 기준

| ID | 확인 | 결과 |
|---|---|---|
| A1-1 | 홈에 상품 24개 표시 | |
| A2-1 | 설문을 바꾸면 추천 순서가 바뀜 | |
| A3-1 · A3-3 | 추천 사유에 "AI 사유" 꼬리표 / `GEMINI_API_KEY`를 빼고 재배포하면 "기본 문구" | |
| A4-1 | 주문 → 새로고침 → 재고 감소 유지, Table Editor에 `source=team` 행 | |
| A5-3 | 두 계정으로 로그인해 "내 주문"이 서로 다름 | |
| S1 | 개발자 도구 Sources에서 `sb_secret_` 값 · `AIza` 검색 결과 없음 | |
| S2 | publishable 키 curl로 orders 조회 → `[]` 또는 42501 | |
| — | 팀 테스트 주문 30건 이상 (`select count(*) from orders where source='team'`) | |
| — | `analysis/queries.sql` SQL Editor 실행 캡처 3장 + 결과 1개 Table Editor 필터로 손 검산 | |

배포 후 데이터가 안 보이면: ① Vercel 환경변수 이름 오타·누락 ② 재배포 여부 ③ 빈 목록이면 RLS 정책, 42501이면 GRANT
