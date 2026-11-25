"""경영정보 MCP 서버 — 도구 3개를 Streamable HTTP로 공개한다.

공식 MCP Python SDK 2.x 기준 (MCPServer — 1.x의 FastMCP를 대체).

실행: python mcp_server/server.py  →  http://localhost:9000/mcp
확인: npx @modelcontextprotocol/inspector  →  Transport: Streamable HTTP, URL: http://localhost:9000/mcp
"""

import json
import logging

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from adapters import exchange, sales, weather
from adapters import offices  # 추가 도구: 해외지사 조회

# SDK 2.x 문서: MCP 레벨 로깅(ctx.info 등)은 deprecated → 서버 로그는 파이썬 logging으로 남긴다
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("business-info")

mcp = MCPServer(
    "business-info",
    instructions=(
        "회사 경영정보 도구 모음. 날씨(get_weather) · 환율(get_exchange) · 국가별 매출(get_sales)을 실제 데이터로 조회한다. "
        "매출을 원화로 환산할 때는 get_sales로 금액 · 통화를 받고 get_exchange로 받은 환율을 곱한다."
    ),
)


def _call(tool: str, fetch, **args) -> str:
    log.info("[MCP CALL] %s %s", tool, json.dumps(args, ensure_ascii=False))
    try:
        return json.dumps(fetch(**args), ensure_ascii=False)
    except (ValueError, RuntimeError) as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def get_weather(city: str) -> str:
    """도시의 현재 날씨(상태 · 기온 · 체감온도 · 습도)를 조회한다.

    Args:
        city: 영문 도시명. 지원: Seoul, New York, Tokyo, Berlin (서울=Seoul, 뉴욕=New York, 도쿄=Tokyo, 베를린=Berlin)
    """
    return _call("get_weather", weather.fetch, city=city)


@mcp.tool()
def get_exchange(base: str, target: str = "KRW") -> str:
    """수출입은행 기준 최근 영업일 환율을 조회한다. base 1단위가 target 몇 단위인지 돌려준다.
    오늘 데이터가 아직 없으면 가장 최근 영업일 값을 쓴다.

    Args:
        base: 기준 통화 ISO 4217 코드. 예: "USD"
        target: 대상 통화 코드. 기본값 "KRW"
    """
    return _call("get_exchange", exchange.fetch, base=base, target=target)


@mcp.tool()
def get_sales(country: str | None = None) -> str:
    """국가별 매출(금액 · 통화)을 조회한다. country를 비우면 전체를 돌려준다.

    Args:
        country: 한글 국가명. 예: "미국", "일본", "독일"
    """
    return _call("get_sales", sales.fetch, country=country)


@mcp.tool()
def get_office(country: str | None = None) -> str:
    """해외지사 정보(국가 · 도시 · 담당자 · 연락처)를 조회한다. country를 비우면 전체 지사를 돌려준다.
    지사가 있는 국가: 미국, 일본, 독일.

    Args:
        country: 한글 국가명. 예: "미국", "일본", "독일"
    """
    return _call("get_office", offices.fetch, country=country)


if __name__ == "__main__":
    # host 기본값 127.0.0.1(로컬 전용, DNS rebinding 보호 기본 적용), 경로 기본값 /mcp — 명시해 둔다
    mcp.run(transport="streamable-http", host="127.0.0.1", port=9000, streamable_http_path="/mcp")
