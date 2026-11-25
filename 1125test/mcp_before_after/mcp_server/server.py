"""경영정보 MCP 서버 — 도구 3개를 Streamable HTTP로 공개한다.

실행: python mcp_server/server.py  →  http://localhost:9000/mcp
확인: npx @modelcontextprotocol/inspector
"""

import json

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from adapters import exchange, sales, weather

mcp = MCPServer("business-info")


def _call(tool: str, fetch, **args) -> str:
    print(f"[MCP CALL] {tool} {json.dumps(args, ensure_ascii=False)}", flush=True)
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


if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=9000)
