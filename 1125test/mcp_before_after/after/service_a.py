"""AI 경영정보비서 — After 버전 (MCP 클라이언트)

외부 API · DB 코드가 하나도 없다. MCP 서버에 붙어서
도구 목록(list_tools)을 받아 Gemini에 넘기고, Gemini가 고른 도구를 call_tool로 그대로 전달한다.

먼저: python mcp_server/server.py
실행: streamlit run after/service_a.py
"""

import asyncio
import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "gemini-3.5-flash"  # 실습 기준은 gemini-3.8-flash. 2026-11-25 503 과부하로 임시 변경
MCP_URL = "http://localhost:9000/mcp"

SYSTEM_PROMPT = (
    "너는 회사의 AI 경영정보비서다. 날씨 · 환율 · 매출 질문에는 반드시 도구로 실제 값을 조회한 뒤 답한다. "
    "매출을 원화로 바꿀 때는 get_exchange로 받은 환율을 곱해서 계산한다. 답은 한국어로 짧고 정확하게."
)


def to_gemini_tools(mcp_tools) -> list[types.Tool]:
    """MCP 도구 설명(이름 · docstring · 스키마)을 Gemini 형식으로 그대로 옮긴다. 손으로 쓰는 스키마 없음."""
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t.name, description=t.description or "", parameters_json_schema=t.input_schema
                )
                for t in mcp_tools
            ]
        )
    ]


async def ask(client: genai.Client, contents: list, log: list) -> str:
    async with streamable_http_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=to_gemini_tools(tools),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
            for _ in range(8):
                resp = await client.aio.models.generate_content(model=MODEL, contents=contents, config=config)
                contents.append(resp.candidates[0].content)
                if not resp.function_calls:
                    return resp.text or ""
                parts = []
                for call in resp.function_calls:
                    args = dict(call.args or {})
                    # if/elif 없음 — 어떤 도구든 이름 그대로 서버에 넘긴다
                    result = await session.call_tool(call.name, args)
                    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
                    payload = {"error": text} if result.is_error else {"result": text}
                    log.append({"tool": call.name, "args": args, "result": payload})
                    parts.append(types.Part.from_function_response(name=call.name, response=payload))
                contents.append(types.Content(role="user", parts=parts))
            return "도구 호출이 너무 많아 중단했습니다."


# ---------------------------------------------------------------- Streamlit 화면

st.set_page_config(page_title="AI 경영정보비서 · After", page_icon="📊")
st.title("AI 경영정보비서")
st.caption(f"After — MCP 서버({MCP_URL})의 도구를 불러 씀 · {MODEL}")

if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    st.session_state.contents = []
    st.session_state.chat = []

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        for item in msg.get("log", []):
            with st.expander(f"[MCP] {item['tool']} {json.dumps(item['args'], ensure_ascii=False)}"):
                body = item["result"].get("result") or item["result"].get("error")
                try:
                    st.json(json.loads(body))
                except (TypeError, ValueError):
                    st.code(body)

if question := st.chat_input("예: 오늘 서울 날씨와 각 나라 매출을 원화로 환산해서 알려줘"):
    st.session_state.chat.append({"role": "user", "text": question})
    st.session_state.contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
    log: list = []
    with st.spinner("조회 중..."):
        try:
            answer = asyncio.run(ask(st.session_state.client, st.session_state.contents, log))
        except Exception as e:  # MCP 서버가 꺼져 있거나 Gemini 호출 실패
            answer = f"오류: {type(e).__name__}: {e}\n\nMCP 서버가 켜져 있는지 확인하세요: `python mcp_server/server.py`"
    st.session_state.chat.append({"role": "assistant", "text": answer, "log": log})
    st.rerun()
