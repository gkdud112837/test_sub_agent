# spec.md v2.1 — 대구 오늘의 식재료 추천 (웹서비스 v1)

> v2 → v2.1 변경: **데이터 · AI 기능 · 보안** 절 추가. 데이터 출처가 코드 안 파일(`data/products.json`)에서 Supabase DB로 바뀜.
> 모든 데이터는 실습용 가상 데이터입니다.

## 1. 한 줄 정의

설문 3문항(가구 수 · 선호 분류 · 예산/조리)에 답하면 재고가 있는 대구 식재료 중 3개를 **룰 점수**로 고르고, **AI가 쓴 추천 사유**와 함께 보여 준다. 주문 버튼을 누르면 주문 로그가 DB에 쌓인다. 쌓인 로그는 12/1 수요예측과 재고 대시보드의 데이터셋이 된다.

## 2. 기능과 수용 기준

| ID | 기능 | 수용 기준 |
|---|---|---|
| F1 | 상품 목록 | A1-1 홈 화면이 `products` 테이블의 행을 표시한다(코드 안 JSON 없음). A1-2 재고 0은 "품절"로 표시 |
| F2 | 설문 → 추천 3개 | A2-1 같은 상품 목록이라도 설문이 다르면 순서가 바뀐다. A2-2 재고 0 · 예산 초과 상품은 나오지 않는다. A2-3 설문은 `surveys`에 1행 저장된다 |
| F3 | AI 추천 사유 | A3-1 추천마다 한 문장 사유(40자 안팎). A3-2 상품 정보에 없는 효능·원산지·수치를 쓰지 않는다(서버가 숫자 포함 응답은 버림). A3-3 키 없음 · 한도 초과 · 시간 초과(8초) · 형식 오류 시 기본 문구가 보이고 화면이 깨지지 않는다 |
| F4 | 주문 버튼 | A4-1 누르면 `orders`에 상품 · 수량 · 시각 · `source=team`이 기록되고 재고가 줄어든다. A4-2 재고보다 많이 주문하면 "재고가 부족해요" |
| F5 | 매직링크 로그인 · 내 주문 | A5-1 이메일 링크로 로그인. A5-2 로그인 주문은 `user_id`가 기록되고, 비로그인 주문은 null. A5-3 "내 주문"에는 본인 주문만 보인다 |

## 3. 데이터

설계 문서: [docs/data_model.md](docs/data_model.md) · SQL: [supabase/schema.sql](supabase/schema.sql), [supabase/policies.sql](supabase/policies.sql)

| 테이블 | 행 | 핵심 열 |
|---|---|---|
| `products` | 24행(예시) | name · category · tags · portion · price · **stock** · created_at |
| `surveys` | 설문 1회 = 1행 | user_id(null 허용) · household · categories · budget · cooking · note · created_at |
| `orders` | 주문 1회 = 1행 | product_id(FK) · qty · **ordered_at** · user_id · survey_id · source(instructor/team) · created_at |

- 강사 제공 가상 주문: `data/instructor_orders.csv` → Table Editor Import (`source=instructor`)
- 팀 테스트 주문: 앱의 주문 버튼으로 30건 이상 (`source=team`, 라벨: 자체 테스트 기록)
- 시각은 UTC로 저장, 집계는 `AT TIME ZONE 'Asia/Seoul'`

## 4. AI 기능

| 항목 | 값 |
|---|---|
| 호출 위치 | 서버 함수 `app/api/recommend` 안에서만 (`lib/gemini.ts`, `server-only`) |
| 모델 | Gemini Flash 계열 무료 등급. `GEMINI_MODEL` 환경변수, 기본 `gemini-flash-latest` |
| 입력 | 추천된 상품 3개의 DB 값(name · category · tags · portion) + 설문 선택지 값. **자유 입력 메모는 넣지 않음** |
| 출력 | 구조화 출력(JSON 스키마) `[{"id": number, "reason": string}]` |
| 서버 검사 | 배열인지 · id가 후보 3개 중 하나인지 · 문자열 · 60자 이하 · 숫자 없음 → 통과한 것만 사용 |
| 실패 처리 | 상품별로 기본 문구(`lib/recommend.ts` fallbackReason, DB 값만으로 조립). 화면에 "AI 사유 / 기본 문구" 꼬리표 |
| 비용 관리 | 추천 1회 = Gemini 호출 1회(3개를 한 번에). 시간 제한 8초. 출력 토큰 512 |

## 5. 보안

- **키**: `SUPABASE_SECRET_KEY` · `GEMINI_API_KEY`는 서버 전용 환경변수다. 브라우저 코드 · 저장소 · 화면 · PR 댓글에 없어야 한다. secret 클라이언트(`lib/supabase/admin.ts`)와 `lib/gemini.ts`는 `import "server-only"`로 브라우저 번들에 들어가면 빌드가 실패한다. 브라우저에는 `NEXT_PUBLIC_SUPABASE_URL` · `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`만 들어간다. 키가 커밋되면 지우는 것으로 끝내지 않고 재발급한다.
- **입력**: 설문 답변은 정해진 선택지 값만 허용(가구 3종 · 분류 6종 중 1~3개 중복 없음 · 예산 3종 · 조리 2종). 자유 입력은 200자 이하, 빈 값이면 null. 주문은 양의 정수 상품 id · 수량 1~20. 요청 본문 4KB 초과는 거부. DB에도 같은 check 제약이 있다(이중 방어).
- **권한**: 모든 테이블 RLS 켬. 쓰기 정책은 하나도 없다 → 쓰기는 서버 함수(secret 키)로만.

  | 테이블 | 읽기 | 쓰기 |
  |---|---|---|
  | products | 누구나 (anon · authenticated) | 서버만 |
  | surveys | 로그인한 본인 행만 | 서버 함수로 추가만, 수정 · 삭제 불가 |
  | orders | 로그인한 본인 행만 | 서버 함수 `place_order`로만 (service_role만 실행 권한) |

  GRANT: anon = products select만, authenticated = products · orders · surveys select, service_role = 전체.
- **AI**: 응답이 JSON 형식이 아니거나 검사를 통과하지 못하면 기본 문구를 보여 준다. 사용자 자유 입력은 프롬프트에 넣지 않는다.
- **오류 메시지**: 사용자에게는 짧은 한국어 문장과 코드만 보인다. DB 오류 원문 · 스택 · 키 이름은 보내지 않고 서버 로그에만 남긴다.
- **로그인 리다이렉트**: `/auth/callback?next=`는 사이트 안 경로(`/`로 시작, `//` 금지)만 허용한다.

## 6. 보안 수용 기준 (사람이 직접 테스트)

| ID | 기준 | 확인 방법 | 로컬 검증 |
|---|---|---|---|
| S1 | 브라우저 개발자 도구 소스에 secret 키 · AI 키 문자열이 없다 | 배포 URL → 개발자 도구 Sources에서 `sb_secret_` 값 · `AIza` 검색 | 빌드 산출물 `.next/static`에서 키 이름 · Gemini 주소 없음 확인 (라이브러리의 접두사 판별 코드 1곳만 있음) |
| S2 | publishable 키로 orders 조회 시 **행 0개** (빈 결과 또는 `42501 permission denied`) | 아래 curl | PGlite로 `42501` 확인 |
| S3 | publishable 키로 orders insert · products update 불가 | 아래 curl | PGlite로 `42501` 확인 |
| S4 | 로그인 사용자 A는 B의 주문 · 설문을 볼 수 없다 | 두 계정으로 "내 주문" 비교 | PGlite로 확인 |
| S5 | `.env.local`이 저장소에 없고 `.env.example`은 이름만 있다 | `git ls-files \| grep env` | 커밋 전 확인 |

```bash
# S2 — publishable 키로 orders 조회 (값은 각자 .env.local에서, 채팅에 붙여 넣지 말 것)
curl "$NEXT_PUBLIC_SUPABASE_URL/rest/v1/orders?select=*" \
  -H "apikey: $NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"
# 기대: [] 또는 {"code":"42501", ...}
```

S2 설명: 교안 예시는 "빈 결과"입니다. 우리 GRANT는 anon에게 orders 권한 자체를 주지 않으므로 RLS까지 가기 전에 `42501`로 막힙니다. GRANT(문)와 RLS(자물쇠)로 두 번 막는 구조이고, 어느 쪽이든 데이터 행은 0개입니다.
