# 데이터 모델 — 대구 오늘의 식재료 추천 (웹서비스 v1)

> 모든 예시 행은 **가상 데이터**입니다. 상품명·가격·재고·주문은 실습용입니다.

## 0. 서비스 문장 → 명사 → 테이블

> "사용자가 **설문**에 답하면, 재고가 있는 **상품** 중 취향에 맞는 3개를 추천 사유와 함께 보여 주고, 주문 버튼을 누르면 **주문**이 기록된다."

| 명사 | 테이블 | 성격 | 이유 |
|---|---|---|---|
| 상품 | `products` | 모두에게 같은 것 | 목록·추천 후보. 재고 수량이 12/1 재고 대시보드의 입력 |
| 설문 | `surveys` | 사람마다 다른 것 | 추천의 근거가 된 취향 기록. 추천 결과를 나중에 재현할 수 있게 저장 |
| 주문 | `orders` | 사람마다 다른 것 | 주문 로그. 날짜별로 모으면 12/1 수요예측 시계열 |

추천 결과(상품 3개 + 사유)는 저장하지 않습니다. 설문과 상품이 있으면 규칙으로 다시 계산할 수 있고, 사유 문장은 매번 달라져도 되는 표시용 값이기 때문입니다. 테이블에 중복으로 두지 않습니다.

## 1. 관계

```text
products 1 ──── N orders     (상품 하나에 주문 여러 개)        orders.product_id → products.id
surveys  1 ──── N orders     (설문 하나에서 주문 여러 개, 선택)  orders.survey_id  → surveys.id
auth.users 1 ── N surveys    (로그인 시만, 비로그인은 null)     surveys.user_id   → auth.users.id
auth.users 1 ── N orders     (로그인 시만, 비로그인은 null)     orders.user_id    → auth.users.id
```

`auth.users`는 Supabase Auth가 관리하는 테이블입니다. 우리가 만들지 않습니다.

## 2. 테이블 정의

### 2-1. `products` — 상품(재고)

| 열 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `id` | bigint (자동 증가) | ✔ | **기본키** |
| `name` | text (1~40자) | ✔ | 상품명 |
| `category` | text | ✔ | `채소` `과일` `정육` `수산` `곡물` `가공` 중 하나 |
| `tags` | text[] | ✔ | 속성 꼬리표. 예: `{간편,구이}`. 추천 규칙과 AI 사유의 **유일한 근거** |
| `portion` | text | ✔ | `1인` `2~3인` `4인+` 중 하나 |
| `price` | integer (원, 0 이상) | ✔ | 판매가 |
| `stock` | integer (0 이상) | ✔ | **재고 수량**. 0이면 추천에서 제외 |
| `created_at` | timestamptz | ✔ | 기본값 `now()` |

| id | name | category | tags | portion | price | stock | created_at |
|---|---|---|---|---|---|---|---|
| 1 | 달성 토마토 | 채소 | {생식,샐러드} | 2~3인 | 4000 | 12 | 2026-11-27 09:00+09 |
| 2 | 군위 한우 국거리 | 정육 | {국물,요리} | 2~3인 | 9000 | 0 | 2026-11-27 09:00+09 |
| 3 | 팔공산 사과 | 과일 | {생식,간식} | 4인+ | 5000 | 7 | 2026-11-27 09:00+09 |

### 2-2. `surveys` — 설문 응답

| 열 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `id` | bigint (자동 증가) | ✔ | **기본키** |
| `user_id` | uuid | | **외래키** → `auth.users.id`. 비로그인은 null |
| `household` | text | ✔ | `1인` `2~3인` `4인+` (products.portion과 같은 값) |
| `categories` | text[] (1~3개) | ✔ | 선호 분류. products.category 값만 허용 |
| `budget` | integer | ✔ | 1개당 최대 가격(원). `5000` `10000` `30000` 중 하나 |
| `cooking` | text | ✔ | `간편` `요리` |
| `note` | text (0~200자) | | 자유 입력. AI 프롬프트에는 넣지 않음(보안 절 참고) |
| `created_at` | timestamptz | ✔ | 기본값 `now()` |

| id | user_id | household | categories | budget | cooking | note | created_at |
|---|---|---|---|---|---|---|---|
| 1 | null | 1인 | {채소,과일} | 5000 | 간편 | 아침 샐러드 | 2026-11-27 10:02+09 |
| 2 | 7f1c…(가상) | 4인+ | {정육} | 30000 | 요리 | null | 2026-11-27 10:15+09 |
| 3 | null | 2~3인 | {수산,채소} | 10000 | 요리 | 주말 저녁 | 2026-11-27 11:40+09 |

### 2-3. `orders` — 주문 로그

| 열 | 형식 | 필수 | 설명 |
|---|---|---|---|
| `id` | bigint (자동 증가) | ✔ | **기본키** |
| `product_id` | bigint | ✔ | **외래키** → `products.id` |
| `qty` | integer (1~20) | ✔ | 수량 |
| `ordered_at` | timestamptz | ✔ | **주문 시각**. 기본값 `now()`. 강사 제공 주문은 CSV의 시각 |
| `user_id` | uuid | | **외래키** → `auth.users.id`. 비로그인 주문은 null |
| `survey_id` | bigint | | **외래키** → `surveys.id`. 추천에서 주문했을 때만 |
| `source` | text | ✔ | `instructor`(강사 제공 가상 주문) · `team`(팀 테스트 주문, 라벨: 자체 테스트 기록) |
| `created_at` | timestamptz | ✔ | 행이 DB에 들어간 시각. 기본값 `now()` |

`ordered_at`과 `created_at`을 따로 두는 이유: CSV로 적재한 과거 주문은 "주문한 시각"(10월)과 "DB에 넣은 시각"(오늘)이 다릅니다. 분석에는 `ordered_at`을 씁니다.

| id | product_id | qty | ordered_at | user_id | survey_id | source | created_at |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 2 | 2026-10-03 18:20+09 | null | null | instructor | 2026-11-27 13:00+09 |
| 2 | 1 | 1 | 2026-11-27 10:03+09 | null | 1 | team | 2026-11-27 10:03+09 |
| 3 | 2 | 1 | 2026-11-27 10:16+09 | 7f1c…(가상) | 2 | team | 2026-11-27 10:16+09 |

## 3. 기능 ↔ 테이블 대응

| spec 기능 | 읽는 테이블 | 쓰는 테이블 | 쓰는 주체 |
|---|---|---|---|
| F1 상품 목록 | products | — | — |
| F2 설문 → 추천 3개 | products | surveys | 서버 함수 (secret 키) |
| F3 AI 추천 사유 | products (name·category·tags·portion) | — | 서버 함수 → Gemini |
| F4 주문 버튼 | products (재고 확인) | orders, products.stock 차감 | 서버 함수 → `place_order` 함수 |
| F5 매직링크 로그인 · 내 주문 | orders, surveys (본인 행) | — | 브라우저 (publishable 키 + RLS) |

## 4. 트랙 점검 (데이터·서비스)

- [x] 재고 열: `products.stock`
- [x] 주문 시각 열: `orders.ordered_at` (timestamptz, UTC 저장 → 조회 시 `AT TIME ZONE 'Asia/Seoul'`)
- [x] 모든 테이블에 `created_at`
- [x] 한 테이블에 모든 것 넣지 않음. 상품 정보는 orders에 복사하지 않고 `product_id`로만 연결
- [x] 예시 행 3개씩으로 검증. 이때 `survey_id`(어느 추천에서 나온 주문인가)와 `ordered_at`/`created_at` 구분이 빠져 있던 것을 찾아 추가함
