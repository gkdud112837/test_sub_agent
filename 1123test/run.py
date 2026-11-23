"""터미널에서 한 번 실행한다.

    python run.py --dry-run     # 가짜 LLM으로 흐름만 확인 (API 키 불필요)
    python run.py               # Gemini로 실제 실행 (.env의 GEMINI_API_KEY 필요)

웹 화면으로 쓰려면 python serve.py
"""

import argparse
import asyncio
import sys

from report_agents.config import ConfigError, load_settings
from report_agents.llm import LLMError
from report_agents.runner import build


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="IT 하드웨어 산업리포트 에이전트 실행")
    ap.add_argument("--dry-run", action="store_true", help="fixtures의 가짜 응답으로 실행")
    ap.add_argument("--no-search", action="store_true", help="Google 검색 단계를 끈다")
    args = ap.parse_args()
    try:
        settings = load_settings()
        run_id, orch = build(settings, dry_run=args.dry_run, use_search=False if args.no_search else None)
        print(f"실행 {run_id} · 모델 {orch.llm.model}")
        path = asyncio.run(orch.run())
    except (ConfigError, LLMError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    print(f"완료: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
