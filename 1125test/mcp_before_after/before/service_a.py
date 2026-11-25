"""AI 경영정보비서 — Before 버전 (MCP 없음)

Gemini SDK의 tool use(function calling)만 쓰고, 외부 연결 3개
(Google 날씨 API · 수출입은행 환율 API · sales.db)를 전부 이 파일 하나에 직접 박아 넣는다.
`# [불편]` 표시는 MCP로 옮기면 사라지는 부담이다.

실행: streamlit run before/service_a.py
"""

import datetime
import json
import os
import sqlite3
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent

# [불편] 1. 서비스마다 키 3개를 각자 .env에서 읽어 들고 있어야 한다
load_dotenv(ROOT / ".env")
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GOOGLE_WEATHER_API_KEY = os.environ["GOOGLE_WEATHER_API_KEY"]
KOREAEXIM_AUTHKEY = os.environ["KOREAEXIM_AUTHKEY"]

MODEL = "gemini-3.5-flash"  # 실습 기준은 gemini-3.8-flash. 2026-11-25 503 과부하로 임시 변경

# [불편] 2. DB 파일 위치와 테이블 구조를 서비스가 직접 알아야 한다
DB_PATH = ROOT / "sales.db"

# [불편] 3. 외부 API 주소가 코드에 박혀 있다
WEATHER_URL = "https://weather.googleapis.com/v1/currentConditions:lookup"
EXCHANGE_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"

# [불편] 4. 날씨 API는 도시명을 모른다 → 도시→위도·경도 표를 서비스가 들고 있어야 한다
CITY_COORDS = {
    "Seoul": (37.5665, 126.9780),
    "New York": (40.7128, -74.0060),
    "Tokyo": (35.6762, 139.6503),
    "Berlin": (52.5200, 13.4050),
}

# [불편] 5. 수출입은행 result 코드의 뜻도 서비스가 외우고 있어야 한다
EXCHANGE_RESULT_CODES = {2: "DATA 코드 오류", 3: "인증코드 오류", 4: "일일 제한횟수 마감"}


# ---------------------------------------------------------------- 외부 연결 3개

def get_weather(city: str) -> dict:
    if city not in CITY_COORDS:
        raise ValueError(f"지원하지 않는 도시: {city} (가능: {', '.join(CITY_COORDS)})")
    lat, lon = CITY_COORDS[city]
    # [불편] 6. 날씨 API는 key=, 환율 API는 authkey= — API마다 인증 방식이 다르다
    resp = requests.get(
        WEATHER_URL,
        params={
            "key": GOOGLE_WEATHER_API_KEY,
            "location.latitude": lat,
            "location.longitude": lon,
            "languageCode": "ko",
        },
        timeout=10,
    )
    resp.raise_for_status()
    raw = resp.json()
    # [불편] 7. 16개쯤 되는 응답 필드 중 쓸 4개를 서비스가 직접 골라낸다
    return {
        "city": city,
        "condition": raw["weatherCondition"]["description"]["text"],
        "temperature_c": raw["temperature"]["degrees"],
        "feels_like_c": raw["feelsLikeTemperature"]["degrees"],
        "humidity_pct": raw["relativeHumidity"],
    }


def _fetch_exchange_table() -> tuple[str, list[dict]]:
    """가장 최근 영업일의 환율표를 받는다. 주말 · 공휴일 · 오전 11시 전에는 빈 목록이 오므로 최대 10일 거슬러 간다."""
    # [불편] 8. 빈 목록이면 하루씩 거슬러 가는 규칙을 서비스가 알아야 한다
    day = datetime.date.today()
    for _ in range(10):
        resp = requests.get(
            EXCHANGE_URL,
            params={"authkey": KOREAEXIM_AUTHKEY, "searchdate": day.strftime("%Y%m%d"), "data": "AP01"},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            code = rows[0].get("result")
            if code != 1:
                raise RuntimeError(f"환율 API 오류: {EXCHANGE_RESULT_CODES.get(code, code)}")
            return day.isoformat(), rows
        day -= datetime.timedelta(days=1)
    raise RuntimeError("최근 10일 동안 환율 데이터가 없습니다")


def _krw_per_unit(rows: list[dict], currency: str) -> float:
    """통화 1단위가 몇 원인지."""
    if currency == "KRW":
        return 1.0
    for row in rows:
        unit = row["cur_unit"]
        # [불편] 9. JPY는 "JPY(100)"처럼 100단위로 온다 → 이름에서 떼어 내고 100으로 나눠야 한다
        code, per = (unit.split("(")[0], int(unit.split("(")[1].rstrip(")"))) if "(" in unit else (unit, 1)
        if code == currency:
            # [불편] 10. 숫자가 "1,346.6" 같은 문자열로 온다 → 쉼표를 지우고 float로 바꿔야 한다
            return float(row["deal_bas_r"].replace(",", "")) / per
    raise ValueError(f"지원하지 않는 통화: {currency}")


def get_exchange(base: str, target: str = "KRW") -> dict:
    base, target = base.upper(), target.upper()
    date, rows = _fetch_exchange_table()
    rate = _krw_per_unit(rows, base) / _krw_per_unit(rows, target)
    return {"base": base, "target": target, "rate": round(rate, 4), "date": date}


def get_sales(country: str | None = None) -> dict:
    # [불편] 11. SQL을 서비스가 직접 쓴다 — 테이블이 바뀌면 이 서비스도 고쳐야 한다
    with sqlite3.connect(DB_PATH) as conn:
        if country:
            cur = conn.execute("SELECT country, amount, currency FROM sales WHERE country = ?", (country,))
        else:
            cur = conn.execute("SELECT country, amount, currency FROM sales")
        rows = cur.fetchall()
    return {"sales": [{"country": c, "amount": a, "currency": cur_} for c, a, cur_ in rows]}


# ---------------------------------------------------------------- LLM에 알려 줄 도구 설명

# [불편] 12. 도구 3개의 JSON 스키마를 손으로 써야 한다 (함수를 바꾸면 여기도 따로 고쳐야 함)
TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_weather",
        description="도시의 현재 날씨(상태 · 기온 · 체감온도 · 습도)를 조회한다.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "enum": list(CITY_COORDS),
                    "description": "영문 도시명. 서울=Seoul, 뉴욕=New York, 도쿄=Tokyo, 베를린=Berlin",
                }
            },
            "required": ["city"],
        },
    ),
    types.FunctionDeclaration(
        name="get_exchange",
        description="수출입은행 기준 최근 영업일 환율을 조회한다. base 1단위가 target 몇 단위인지 돌려준다.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "base": {"type": "string", "description": "기준 통화 ISO 4217 코드. 예: USD"},
                "target": {"type": "string", "description": "대상 통화 코드. 기본값 KRW", "default": "KRW"},
            },
            "required": ["base"],
        },
    ),
    types.FunctionDeclaration(
        name="get_sales",
        description="국가별 매출(금액 · 통화)을 조회한다. country를 비우면 전체를 돌려준다.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "한글 국가명. 예: 미국, 일본, 독일"}
            },
        },
    ),
]


def run_tool(name: str, args: dict) -> dict:
    # [불편] 13. LLM이 고른 도구 이름을 보고 어느 함수를 부를지 if/elif로 직접 나눈다
    try:
        if name == "get_weather":
            return {"result": get_weather(args["city"])}
        elif name == "get_exchange":
            return {"result": get_exchange(args["base"], args.get("target", "KRW"))}
        elif name == "get_sales":
            return {"result": get_sales(args.get("country"))}
        else:
            return {"error": f"알 수 없는 도구: {name}"}
    except (ValueError, RuntimeError, requests.RequestException) as e:
        # 키가 들어 있는 URL이 화면에 새지 않도록 예외 종류만 남긴다
        msg = str(e) if not isinstance(e, requests.RequestException) else f"{type(e).__name__} (외부 API 호출 실패)"
        return {"error": f"{name} 실패: {msg}"}


# ---------------------------------------------------------------- Gemini 대화 루프

SYSTEM_PROMPT = (
    "너는 회사의 AI 경영정보비서다. 날씨 · 환율 · 매출 질문에는 반드시 도구로 실제 값을 조회한 뒤 답한다. "
    "매출을 원화로 바꿀 때는 get_exchange로 받은 환율을 곱해서 계산한다. 답은 한국어로 짧고 정확하게."
)


def ask(client: genai.Client, contents: list, log: list) -> str:
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for _ in range(8):  # 도구 호출이 끝없이 이어지지 않게 상한
        resp = client.models.generate_content(model=MODEL, contents=contents, config=config)
        contents.append(resp.candidates[0].content)
        if not resp.function_calls:
            return resp.text or ""
        parts = []
        for call in resp.function_calls:
            args = dict(call.args or {})
            result = run_tool(call.name, args)
            log.append({"tool": call.name, "args": args, "result": result})
            parts.append(types.Part.from_function_response(name=call.name, response=result))
        contents.append(types.Content(role="user", parts=parts))
    return "도구 호출이 너무 많아 중단했습니다."


# ---------------------------------------------------------------- Streamlit 화면

st.set_page_config(page_title="AI 경영정보비서 · Before", page_icon="📊")
st.title("AI 경영정보비서")
st.caption(f"Before — MCP 없이 파일 하나에 외부 연결 3개를 직접 연결 · {MODEL}")

if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=GEMINI_API_KEY)
    st.session_state.contents = []  # Gemini에 보내는 전체 대화
    st.session_state.chat = []      # 화면에 그릴 말풍선

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        for item in msg.get("log", []):
            with st.expander(f"[TOOL] {item['tool']} {json.dumps(item['args'], ensure_ascii=False)}"):
                st.json(item["result"])

if question := st.chat_input("예: 오늘 서울 날씨와 각 나라 매출을 원화로 환산해서 알려줘"):
    st.session_state.chat.append({"role": "user", "text": question})
    st.session_state.contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    log: list = []
    with st.spinner("조회 중..."):
        try:
            answer = ask(st.session_state.client, st.session_state.contents, log)
        except Exception as e:  # Gemini 호출 자체가 실패한 경우
            answer = f"오류: {type(e).__name__}: {e}"
    st.session_state.chat.append({"role": "assistant", "text": answer, "log": log})
    st.rerun()
