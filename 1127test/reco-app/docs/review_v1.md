# review_v1 — 보안·품질 리뷰 (리뷰 서브에이전트)

- 일시: 2026-11-27 · 리뷰어: 구현 대화와 분리된 서브에이전트(읽기 전용, 파일 수정 없음)
- 범위: `reco-app/` 전체(아직 커밋 전이라 main 대비 변경분 = 전체) · 기준: `spec.md` 5절 보안 · 6절 보안 수용 기준
- 점검 항목: ① 브라우저 키 노출 ② 입력 검증 · AI 응답 검사 ③ RLS · GRANT ④ 오류 메시지 + 기타(정확성 · 남용)
- 진행: 1차 리뷰 → 메인 세션 수정 → **같은 리뷰 재실행**(2차) → 2차에서 새로 나온 N1~N4 수정

## 결과 요약

| 심각도 | 1차 발견 | 남은 것 |
|---|---|---|
| 높음 | 0 | **0** |
| 중간 | 5 (#1~#5) + 2차 N1 | 0 (#3·#4 메모리 레이트 리밋은 "최선 노력"으로 수용, 운영 전 공유 저장소로 교체) |
| 낮음 | 8 (#6~#13) + 2차 N2~N4 | #13 전체 CSP (v1.5) |

## 발견 목록과 조치

| # | 항목 | 문제 | 위치 | 심각도 | 조치 | 상태 |
|---|---|---|---|---|---|---|
| 1 | 기타 | **오픈 리다이렉트**: `next=/%09/evil.example`이 접두사 검사를 통과한 뒤 `new URL()`이 탭을 지워 외부로 이동함. 메인 세션에서도 재현함 | app/auth/callback/route.ts | 중간 | `lib/redirect.ts`: URL을 해석한 뒤 origin 비교. 회귀 테스트 `scripts/test_redirect.ts` 9건 PASS | 해결 |
| 2 | ③ | GRANT만 있고 revoke가 없어, 프로젝트 기본 권한이 anon에 ALL이면 "anon = products select만"이 깨짐 | supabase/schema.sql 4절 | 중간 | `revoke all` → 필요한 grant. verify 스크립트가 열린 기본 권한을 흉내 내도록 바꿈 | 해결 |
| 3 | 기타 | 레이트 리밋 없음 → 비로그인 반복 주문으로 재고를 0으로 만들 수 있고 주문 로그도 오염됨 | app/api/orders/route.ts | 중간 | 비로그인 분당 5회 · 1회 3개, 로그인 분당 20회 (`lib/rateLimit.ts`) | 부분(메모리 저장) |
| 4 | 기타 | `/api/recommend` 반복 호출로 Gemini 한도 소진 · surveys가 쌓임 | app/api/recommend/route.ts | 중간 | 비로그인 분당 5회 · 로그인 10회, 설문 저장 · AI 호출 전에 검사 | 부분(메모리 저장) |
| 5 | 기타 | 세션 갱신 미들웨어 없음 → 토큰 만료 뒤 `/me`가 로그아웃처럼 보일 수 있음 | lib/supabase/server.ts | 중간 | `proxy.ts`(Next 16)에서 `getUser()`로 갱신 | 해결(런타임 확인 필요) |
| 6 | ② | 숫자 금지 검사가 ASCII `\d`만 막음 | lib/gemini.ts | 낮음 | `\p{Nd}` · 전각 · 단위 · 한글 수사 일부 | 부분(수용) |
| 7 | ② | 4KB 제한을 글자 수로 잼 | lib/http.ts | 낮음 | 스트림 바이트 누적, 상한을 넘으면 중단 | 해결 |
| 8 | 기타 | Content-Type 미확인 → text/plain 교차 사이트 POST 가능 | lib/http.ts | 낮음 | `application/json` 필수 + Origin host 비교 → 415 | 해결 |
| 9 | 기타 | 없는 상품도 "재고 부족"으로 응답 | schema.sql place_order | 낮음 | `NO_PRODUCT` 예외 → 404 | 해결 |
| 10 | 기타 | 비로그인 사용자가 남의 비로그인 설문에 주문을 연결할 수 있음 | app/api/orders/route.ts | 낮음 | 로그인 본인 설문만 연결 | 해결 |
| 11 | ④ | `/login?error=1` 안내 없음 | app/login/page.tsx | 낮음 | 링크 만료 · 다른 브라우저 안내 | 해결 |
| 12 | ④ | 설문 수 조회 실패를 "0회"로 표시 | app/me/page.tsx | 낮음 | 실패 시 "-" | 해결 |
| 13 | 기타 | 보안 헤더 없음 | (next.config 없음) | 낮음 | XFO · frame-ancestors · nosniff · Referrer · Permissions, poweredBy 끔 | 부분(전체 CSP는 v1.5) |
| N1 | 기타 | 레이트 리밋 키가 위조 가능한 XFF 첫 값 | lib/rateLimit.ts | 중간 | `x-vercel-forwarded-for` → `x-real-ip` → XFF 마지막 값 | 해결(배포 확인 필요) |
| N2 | 성능 | proxy가 `/api`까지 돌아 Auth 호출이 2번 | proxy.ts | 낮음 | matcher에서 `api/` 제외 | 해결 |
| N3 | ③ | revoke가 앞으로 만들 테이블에는 적용 안 됨 | schema.sql | 낮음 | `alter default privileges ... revoke` 추가 | 해결 |
| N4 | ② | 단위 정규식 `g`가 영어 단어 안에도 걸림 | lib/gemini.ts | 낮음 | 영문자 경계에서만 매칭 | 해결 |

## 리뷰어가 "문제 없음"으로 확인한 것 (요약)

- `"use client"` 파일 4개는 `admin.ts` · `gemini.ts` · `server.ts`를 import하지 않음. 세 모듈 모두 `import "server-only"`
- `SUPABASE_SECRET_KEY`는 `admin.ts`에서만, `GEMINI_API_KEY`는 `gemini.ts`에서만 읽음. 저장소에 키 값 패턴 0건, `.env.local` 없음
- API 응답에는 `{ok, code, message}` 또는 공개 필드만 있음. DB 오류 원문은 서버 로그에만 남음
- 입력 검증 ↔ DB check 제약 일치(이중), 주문 수량은 삼중 방어
- 프롬프트에 자유 입력이 들어가지 않음. JSON.parse 예외 처리, 8초 타임아웃, 실패 시 기본 문구
- RLS 3개 테이블 모두 켜짐. 정책은 select 3개뿐이고 쓰기 정책은 0개. `place_order`는 security invoker + `search_path` 고정 + service_role만 EXECUTE
- 재고 차감은 조건부 update 한 문장이라 경쟁 조건에 안전함. 서버는 `getUser()`로 토큰을 검증함

## 이 리뷰가 보지 못한 범위 → 사람이 확인

- 실제 Supabase 프로젝트의 기본 권한 · Auth 설정(Redirect URL, OTP 제한)
- Vercel에서 IP 헤더 동작, 여러 인스턴스에서 레이트 리밋 효과, 1시간 뒤 토큰 갱신
- 실제 Gemini 응답 · 안전 필터 차단 시 동작, npm 의존성 취약점
- **"문제 없음"이 안전을 보장하지는 않는다.** 보안 수용 기준 S1~S5는 `docs/deploy_checklist.md` C절에서 사람이 배포 URL로 테스트한다.

## 남은 항목 (progress로 이월)

1. 레이트 리밋 저장소를 Upstash/Vercel KV로 교체 (#3 · #4)
2. 전체 CSP 헤더 (#13)
3. 수치 표현 금칙어 보강: 하나 · 둘 · 셋 등 (#6)
