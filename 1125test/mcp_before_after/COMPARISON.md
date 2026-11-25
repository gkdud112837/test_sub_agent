# MCP 전후 비교 — AI 경영정보비서

같은 챗봇(날씨 · 환율 · 매출을 묻는 AI 경영정보비서)을 두 방식으로 만들어 비교했다.

- **Before** — MCP 없이 Gemini SDK tool use만으로, 외부 연결 3개를 파일 하나에 직접 연결
- **After** — 외부 연결을 MCP 서버로 떼어 내고, 챗봇은 MCP 클라이언트로 도구를 불러 씀

## 1. 한 줄 결론

> **외부 API · DB를 "어떻게 부르는지"가 서비스에서 MCP 서버로 옮겨 갔다.**
> 서비스는 "무슨 도구가 있는지"만 물어보고(`list_tools`), "이 도구 실행해 줘"(`call_tool`)라고만 한다.

## 2. 구조

**Before** — 전부 한 파일

```
before/service_a.py
 ├─ Streamlit 화면
 ├─ Gemini 대화 루프
 ├─ 도구 스키마 (손으로 작성)
 ├─ if/elif 분기
 ├─ 날씨 API  ──▶ Google Weather
 ├─ 환율 API  ──▶ 한국수출입은행
 └─ SQL       ──▶ sales.db
```

**After** — 서비스와 연결 코드 분리

```
after/service_a.py                         mcp_server/server.py  (도구 3개 공개)
 ├─ Streamlit 화면     list_tools           └─ adapters/
 └─ Gemini 대화 루프  ───────────────▶          ├─ weather.py   ──▶ Google Weather
                       call_tool                ├─ exchange.py  ──▶ 한국수출입은행
                  (localhost:9000/mcp)          └─ sales.py     ──▶ sales.db
```

## 3. 숫자로 보는 차이

| 항목 | Before | After |
|---|---|---|
| 서비스 파일 줄 수 | 251줄 | **108줄** |
| 서비스가 들고 있는 외부 키 | 3개 (Gemini · 날씨 · 환율) | **1개** (Gemini만) |
| 서비스 안의 외부 API 주소 · SQL | 있음 (URL 2개 · SQL 2개) | **없음** |
| 손으로 쓴 도구 JSON 스키마 | 3개 | **0개** (서버가 docstring · 타입 힌트로 자동 생성) |
| 도구 분기 (`if/elif`) | 있음 | **없음** (이름 그대로 `call_tool`) |
| `# [불편]` 표시 | 13곳 | 0곳 |
| 연결 코드 위치 | 서비스 안 | `mcp_server/` (server 58줄 + adapters 129줄) |

전체 줄 수만 보면 After 쪽(서비스 108 + 서버 187)이 더 많다. **핵심은 줄 수가 아니라 연결 코드가 "한 곳"에 모였다는 것** — 서비스가 2개, 3개로 늘어나도 서버 코드는 그대로 재사용된다.

## 4. `# [불편]` 13곳은 어디로 갔나

| # | Before에서 서비스가 떠안던 일 | After |
|---|---|---|
| 1 | 키 3개를 `.env`에서 각자 읽기 | 날씨 · 환율 키는 서버만 읽음 |
| 2 | DB 파일 위치 · 테이블 구조 알기 | `adapters/sales.py` |
| 3 | 외부 API 주소 하드코딩 | `adapters/weather.py`, `exchange.py` |
| 4 | 도시 → 위도 · 경도 표 | `adapters/weather.py` |
| 5 | 수출입은행 result 코드(2 · 3 · 4) 뜻 | `adapters/exchange.py` |
| 6 | API마다 다른 인증 방식 (`key=` vs `authkey=`) | 각 어댑터 |
| 7 | 날씨 응답 16개 필드 중 4개 골라내기 | `adapters/weather.py` |
| 8 | 빈 날짜면 최대 10일 거슬러 가기 | `adapters/exchange.py` |
| 9 | `JPY(100)` → 100으로 나누기 | `adapters/exchange.py` |
| 10 | `"1,346.6"` 쉼표 제거 후 숫자 변환 | `adapters/exchange.py` |
| 11 | SQL 직접 작성 | `adapters/sales.py` |
| 12 | 도구 JSON 스키마 손으로 작성 | `@mcp.tool()` + docstring으로 자동 생성 |
| 13 | 도구 이름 보고 `if/elif`로 분기 | `session.call_tool(name, args)` 한 줄 |

## 5. 코드로 보는 차이

**도구 설명 — Before: 손으로 쓴 스키마**

```python
types.FunctionDeclaration(
    name="get_exchange",
    description="수출입은행 기준 최근 영업일 환율을 조회한다...",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "base": {"type": "string", "description": "기준 통화 ISO 4217 코드. 예: USD"},
            "target": {"type": "string", "description": "대상 통화 코드. 기본값 KRW", "default": "KRW"},
        },
        "required": ["base"],
    },
)
```

**도구 설명 — After: 서버 함수 하나가 곧 스키마**

```python
@mcp.tool()
def get_exchange(base: str, target: str = "KRW") -> str:
    """수출입은행 기준 최근 영업일 환율을 조회한다...

    Args:
        base: 기준 통화 ISO 4217 코드. 예: "USD"
        target: 대상 통화 코드. 기본값 "KRW"
    """
```

함수 이름 = 도구 이름, docstring = 설명, 타입 힌트 = 스키마. 클라이언트는 `list_tools()`로 받아 Gemini에 그대로 넘긴다.

**도구 실행 — Before: 분기**

```python
if name == "get_weather":
    return {"result": get_weather(args["city"])}
elif name == "get_exchange":
    return {"result": get_exchange(args["base"], args.get("target", "KRW"))}
elif name == "get_sales":
    return {"result": get_sales(args.get("country"))}
```

**도구 실행 — After: 한 줄**

```python
result = await session.call_tool(call.name, args)
```

## 6. 실행 결과 (2026-11-25, 같은 질문)

질문: *"서울 날씨 알려주고, 나라별 매출을 원화로 환산해서 합계까지 알려줘"*

| | Before | After |
|---|---|---|
| 도구 호출 | get_weather(Seoul) · get_sales() · get_exchange(USD / JPY / EUR) | 동일 (서버 로그에 `[MCP CALL]` 5건) |
| 서울 날씨 | 맑음, 2℃ (체감 1℃), 습도 55% | 동일 |
| 환율 | USD 1,343.6 · JPY 8.4341 · EUR 1,472.72 | 동일 |
| 매출 합계 | **129,300,300원** | **129,300,300원** |

→ **사용자 입장에서 결과는 똑같다.** 바뀐 것은 내부 구조뿐이다.

에러도 서버가 정리해서 돌려준다. 지원하지 않는 도시를 넣으면:

```
get_weather("Busan") → isError=True
"지원하지 않는 도시: Busan (가능: Seoul, New York, Tokyo, Berlin)"
```

키가 담긴 URL은 LLM에게 새지 않고, 사람이 읽을 수 있는 메시지만 전달된다.

## 7. 결과적으로 무엇이 좋아졌나

1. **재사용** — 서비스 B를 만들 때 Before는 연결 코드를 통째로 복사해야 하지만, After는 서버 주소만 알면 된다. Claude Code 같은 다른 AI 도구도 같은 서버에 붙을 수 있다.
2. **변경이 한 곳** — 환율 API 형식이나 DB 테이블이 바뀌면 Before는 서비스마다 고쳐야 하고, After는 어댑터 하나만 고치면 된다.
3. **보안** — 날씨 · 환율 키가 서비스에서 사라지고 서버에만 남는다.
4. **확장** — 도구를 추가할 때 `@mcp.tool()` 함수 하나만 쓰면, 붙어 있는 모든 서비스가 다음 `list_tools()`에서 자동으로 알게 된다. 서비스 코드는 손대지 않는다.
5. **역할 분리** — 서비스는 "대화와 화면", 서버는 "외부 연결"만 책임진다.

**대가:** 서버를 하나 더 띄워야 하고(`python mcp_server/server.py`), 서버가 꺼지면 After 서비스는 도구를 못 쓴다. 서비스가 하나뿐이고 바뀔 일도 없다면 Before 방식이 더 단순할 수 있다.

## 8. 참고 — 실습 환경 메모

- 실습 기준 모델은 `gemini-3.8-flash`지만, 2026-11-25 당시 구글 쪽 용량 부족으로 503 · 504가 계속 나서 두 서비스 모두 `gemini-3.5-flash`로 바꿔 실행했다.
- 무료 등급은 모델당 분당 5회 한도가 있다. 질문 하나에 Gemini를 3~4번 부르므로 연속 질문 시 429가 날 수 있다.
