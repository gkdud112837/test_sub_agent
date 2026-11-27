# CLAUDE.md — daegu-reco-app

대구 오늘의 식재료 개인화 추천 웹앱 (Next.js App Router + Supabase + Gemini). 기준 문서는 `spec.md`(v2.1), `docs/data_model.md`.

## 구조
- `app/` 화면 · `app/api/` 서버 함수(비밀 키는 여기서만) · `lib/` 공용 로직 · `supabase/` SQL · `analysis/` 집계 쿼리

## DB 규칙
- 스키마 · 정책 변경은 `supabase/*.sql` 파일로만 한다. 실행은 사람이 SQL Editor에서 `schema.sql` → `policies.sql` 순서로 한다.
- 모든 테이블은 `created_at`이 있고 RLS가 켜져 있다. 새 테이블에는 GRANT와 정책을 같은 PR에 넣는다.
- 쓰기(insert · update)는 서버 함수의 secret 클라이언트로만 한다. 브라우저 쪽에서 쓰는 정책은 만들지 않는다. 필요하면 spec 보안 절에 이유를 먼저 적는다.
- 시각은 timestamptz(UTC). 날짜 · 요일 집계는 `AT TIME ZONE 'Asia/Seoul'`.
- SQL Editor는 관리자 권한(RLS 미적용)이다. 분석은 SELECT만 쓴다.
- 로컬 검증: `npm run verify:sql` (PGlite로 schema · policies · RLS · queries 실행)

## 환경변수 (이름만. 값은 묻지도 쓰지도 않는다)
| 이름 | 위치 |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | 브라우저 가능 |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | 브라우저 가능 (RLS가 허락한 행만) |
| `SUPABASE_SECRET_KEY` | 서버 전용 — `lib/supabase/admin.ts`만 읽음 |
| `GEMINI_API_KEY` | 서버 전용 — `lib/gemini.ts`만 읽음 |
| `GEMINI_MODEL` | 선택, 서버 |

- 값은 `.env.local`(커밋 금지)과 Vercel Project Settings(Production · Preview)에 같은 이름으로 넣는다.
- 클라이언트 컴포넌트(`"use client"`)에서 `lib/supabase/admin.ts` · `lib/gemini.ts`를 import 하지 않는다.

## 작업 흐름
- 스펙 → 계획 모드 → 구현 → `npm run build` · `npm run verify:sql` → 리뷰 서브에이전트(`docs/review_v1.md`) → 커밋
- DB 변경 PR 본문은 `docs/pr_db_checklist.md`의 네 항목을 채운다.
