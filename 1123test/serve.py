"""로컬 웹 화면을 띄운다.

    python serve.py   →  http://127.0.0.1:8770  (.env의 WEB_HOST, WEB_PORT)
"""

import sys

from report_agents.config import ConfigError
from report_agents.server import serve

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        serve()
    except ConfigError as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
