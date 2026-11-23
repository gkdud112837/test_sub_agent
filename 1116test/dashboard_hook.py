"""대시보드용 Claude Code 훅. SubagentStart/SubagentStop 이벤트를 한 줄씩 기록한다.

dashboard_server.py가 실행할 때 --settings로 연결하며, 기록 위치는 환경변수 DASHBOARD_EVENTS로 받는다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

path = os.environ.get("DASHBOARD_EVENTS")
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except ValueError:
    data = {}
record = {k: data.get(k) for k in ("hook_event_name", "agent_type", "agent_id", "session_id")}
record["t"] = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
if path:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
sys.exit(0)
