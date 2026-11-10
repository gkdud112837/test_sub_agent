"""Claude Code 훅 이벤트 기록기.

Claude Code가 stdin으로 넘겨주는 훅 JSON을 받아
<프로젝트 루트>/.claude/logs/events.jsonl 에 한 줄(JSON)씩 추가한다.

- ts            : 이벤트 기록 시각 (Unix epoch, 초 단위 정수)
- tool_response : 길 수 있으므로 앞 600자만 남긴다 (문자열로 변환 후 자름)
- tool_input · prompt : 안의 긴 문자열을 600자로 자르고 생략한 글자 수를 표시한다
- 프로젝트 루트 : 환경 변수 VOC_PROJECT_ROOT → CLAUDE_PROJECT_DIR → 이 파일 기준 상위 폴더 순으로 찾는다

훅이 Claude Code 작업을 막지 않도록 어떤 오류가 나도 exit 0으로 끝낸다.
"""
import json
import os
import sys
import time

ENV_ROOT = "VOC_PROJECT_ROOT"
MAX_RESPONSE = 600


def project_root() -> str:
    for key in (ENV_ROOT, "CLAUDE_PROJECT_DIR"):
        val = os.environ.get(key)
        if val and os.path.isdir(val):
            return val
    # .claude/hooks/log_event.py → 두 단계 위가 프로젝트 루트
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def clip(value):
    """문자열은 600자로 자르고(잘렸으면 원래 길이 표시), dict · list는 안쪽 문자열까지 자른다."""
    if isinstance(value, str):
        if len(value) > MAX_RESPONSE:
            return value[:MAX_RESPONSE] + f"…[+{len(value) - MAX_RESPONSE}자 생략]"
        return value
    if isinstance(value, dict):
        return {k: clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clip(v) for v in value]
    return value


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {"payload": data}
    except json.JSONDecodeError:
        data = {"raw": raw[:MAX_RESPONSE], "parse_error": True}

    record = {"ts": int(time.time())}
    record.update(data)

    # tool_input(Write의 content 등)과 긴 프롬프트도 600자로 자른다
    if "tool_input" in data:
        record["tool_input"] = clip(data["tool_input"])
    if isinstance(data.get("prompt"), str):
        record["prompt"] = clip(data["prompt"])

    if "tool_response" in data:
        resp = data["tool_response"]
        text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
        record["tool_response"] = text[:MAX_RESPONSE]
    else:
        record["tool_response"] = ""

    log_dir = os.path.join(project_root(), ".claude", "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 기록 실패가 작업을 막지 않게 한다
        print(f"log_event: {e}", file=sys.stderr)
    sys.exit(0)
