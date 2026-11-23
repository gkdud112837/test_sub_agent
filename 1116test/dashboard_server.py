"""에이전트 대시보드 서버.

실행:  python -X utf8 dashboard_server.py   →  http://127.0.0.1:8765

- GET  /                 dashboard.html
- GET  /api/folders      분석 폴더 목록 (예시 모델 + ideas/*)
- GET  /api/state        실행 상태, 에이전트 상태, run_log, 손익, 리뷰 지적사항
- POST /api/run          {"idea": "..."} → claude -p 로 playbook.md 절차 실행
- POST /api/stop         실행 중인 claude 프로세스 트리 종료

에이전트 상태는 두 신호로 판단한다.
1) claude의 stream-json 출력: Agent 도구 호출(시작), 서브에이전트 메시지(작업 중), 도구 결과(종료)
2) SubagentStart/SubagentStop 훅(dashboard_hook.py)이 남기는 .dashboard/agent_events.jsonl
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, ".dashboard")
EVENTS_PATH = os.path.join(STATE_DIR, "agent_events.jsonl")
STREAM_PATH = os.path.join(STATE_DIR, "stream.jsonl")
SETTINGS_PATH = os.path.join(STATE_DIR, "run_settings.json")
HOOK_PATH = os.path.join(ROOT, "dashboard_hook.py")
EXAMPLE_MODEL = "market_model_case_student.xlsx"
AGENTS = ["researcher", "competitor-analyzer", "model-simulator", "reviewer"]
ALLOWED_TOOLS = "Agent,Task,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Bash"
PORT = int(os.environ.get("DASHBOARD_PORT", "8765"))
KST = timezone(timedelta(hours=9))

PROMPT = """playbook.md 절차(0~10단계)로 아래 새 사업 아이디어를 분석해줘.

아이디어: {idea}
작업 폴더: {folder} (model.xlsx, report.md, run_log.json을 이 폴더에 만든다)

- CLAUDE.md의 작성 규칙과 run_log.json 원칙을 지킨다. 단계가 끝날 때마다 {folder}/run_log.json에 기록을 추가한다.
- 1~2단계 자료·가정은 researcher, 8~9단계는 competitor-analyzer 서브에이전트에게 맡기고 두 에이전트는 동시에 돌린다.
- 2~7단계 모델 작성·계산은 model-simulator, 10단계 심사는 reviewer 서브에이전트에게 맡긴다.
- 이 실행은 대시보드에서 자동으로 돌고 있어 사용자에게 질문할 수 없다. 필요한 결정은 직접 하고 decisions에 근거를 남긴다. 모르는 사실은 [확인필요]로 둔다.
- 커밋과 푸시는 하지 않는다.
"""


EXAMPLE_PROMPT = """playbook.md 절차(0~10단계)로 예시 모델 market_model_case_student.xlsx(D마트 즉시배송)를 분석해줘.

작업 폴더: . (이 폴더. 기록은 ./run_log.json, 보고서는 ./report.md)

- 이미 있는 엑셀 모델을 각 단계의 입력·결과로 사용한다. 원본 엑셀은 수정하지 않는다. 고칠 점은 해당 단계의 validation, better_direction, reviewer의 findings에 남긴다.
- CLAUDE.md의 작성 규칙과 run_log.json 원칙을 지킨다. 단계가 끝날 때마다 ./run_log.json에 기록을 추가한다. 5단계 기록의 pnl은 손익 시트 12행 값을 셀 주소와 함께 넣는다.
- 1~2단계 자료·가정 점검은 researcher, 8~9단계는 competitor-analyzer 서브에이전트에게 맡기고 두 에이전트는 동시에 돌린다.
- 3~7단계 결과 정리와 타당성 확인은 model-simulator(엑셀 수정 금지), 10단계 심사는 reviewer 서브에이전트에게 맡긴다.
- 이 실행은 대시보드에서 자동으로 돌고 있어 사용자에게 질문할 수 없다. 필요한 결정은 직접 하고 decisions에 근거를 남긴다. 모르는 사실은 [확인필요]로 둔다.
- 커밋과 푸시는 하지 않는다.
"""


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


lock = threading.Lock()
proc = None
run = {}
instances = {}      # agent -> set(instance keys); 비어 있지 않으면 작업 중
tool_to_agent = {}  # Agent 도구 호출 id -> 에이전트 이름
agentid_to_agent = {}
hook_seen = False
events_pos = 0


def reset_run():
    global run, instances, tool_to_agent, agentid_to_agent, hook_seen
    run = {
        "running": False, "stopping": False, "pid": None, "idea": None, "folder": None,
        "started_at": None, "ended_at": None, "exit_code": None,
        "agents": {a: {"status": "idle", "since": None, "activity": None, "runs": 0} for a in AGENTS},
        "feed": [],
    }
    instances = {a: set() for a in AGENTS}
    tool_to_agent, agentid_to_agent, hook_seen = {}, {}, False


reset_run()


def feed(who, text):
    run["feed"].append({"t": now(), "who": who, "text": text[:300]})
    del run["feed"][:-200]


def norm_agent(name):
    if not name:
        return None
    name = str(name).split(":")[-1].strip()
    return name if name in AGENTS else None


def agent_start(agent, key, activity=None):
    a = run["agents"][agent]
    if not instances[agent]:
        a["since"] = now()
        a["runs"] += 1
        feed(agent, "작업 시작" + (f": {activity}" if activity else ""))
    instances[agent].add(key)
    a["status"] = "running"
    if activity:
        a["activity"] = activity


def agent_end(agent, key=None, error=False):
    keys = instances[agent]
    if key in keys:
        keys.discard(key)
    elif keys and key is None:
        keys.pop()
    if not keys and run["agents"][agent]["status"] == "running":
        run["agents"][agent]["status"] = "error" if error else "done"
        run["agents"][agent]["since"] = now()
        feed(agent, "오류로 종료" if error else "작업 완료")


def short_input(inp):
    if not isinstance(inp, dict):
        return ""
    for k in ("description", "query", "file_path", "url", "pattern", "command", "prompt"):
        if inp.get(k):
            return str(inp[k]).replace("\n", " ")[:80]
    return ""


def result_text(block):
    c = block.get("content")
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return str(c or "")


def handle(msg):
    t = msg.get("type")
    parent = msg.get("parent_tool_use_id")
    if t == "system" and msg.get("subtype") == "init":
        feed("main", "세션 시작")
        return
    if t == "result":
        feed("main", f"실행 종료 ({msg.get('subtype', '')})")
        return
    content = (msg.get("message") or {}).get("content")
    if not isinstance(content, list):
        return
    sub_agent = tool_to_agent.get(parent) if parent else None
    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if t == "assistant" and bt == "tool_use":
            name, inp = block.get("name"), block.get("input") or {}
            if name in ("Agent", "Task"):
                agent = norm_agent(inp.get("subagent_type"))
                if agent:
                    tool_to_agent[block.get("id")] = agent
                    agent_start(agent, block.get("id"), inp.get("description"))
                    feed("main", f"{agent} 호출: {inp.get('description', '')}")
            elif sub_agent:
                if run["agents"][sub_agent]["status"] != "running":
                    agent_start(sub_agent, parent)
                run["agents"][sub_agent]["activity"] = f"{name} · {short_input(inp)}".strip(" ·")
            else:
                feed("main", f"{name} · {short_input(inp)}".strip(" ·"))
        elif t == "assistant" and bt == "text" and not sub_agent and block.get("text", "").strip():
            feed("main", block["text"].strip().replace("\n", " "))
        elif t == "user" and bt == "tool_result":
            tid = block.get("tool_use_id")
            agent = tool_to_agent.get(tid)
            if agent:
                text = result_text(block).lower()
                # 백그라운드로 띄운 경우 결과가 바로 돌아오므로 종료로 보지 않는다(훅의 SubagentStop을 기다린다)
                launched = "background" in text or "백그라운드" in text or "launched" in text
                if block.get("is_error"):
                    agent_end(agent, tid, error=True)
                elif not launched:
                    agent_end(agent, tid)


def poll_hook_events():
    global events_pos, hook_seen
    if not os.path.exists(EVENTS_PATH):
        return
    with open(EVENTS_PATH, encoding="utf-8") as f:
        f.seek(events_pos)
        lines = f.readlines()
        events_pos = f.tell()
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        name = ev.get("hook_event_name")
        agent = norm_agent(ev.get("agent_type")) or agentid_to_agent.get(ev.get("agent_id"))
        if not agent:
            continue
        hook_seen = True
        if name == "SubagentStart":
            agentid_to_agent[ev.get("agent_id")] = agent
            agent_start(agent, "hook:" + str(ev.get("agent_id")))
        elif name == "SubagentStop":
            agent_end(agent, "hook:" + str(ev.get("agent_id")))
            # 같은 에이전트의 stream 신호(도구 호출 id)도 하나 정리한다
            for k in list(instances[agent]):
                if not k.startswith("hook:"):
                    agent_end(agent, k)
                    break


def reader(p):
    with open(STREAM_PATH, "a", encoding="utf-8") as raw:
        for line in p.stdout:
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            raw.write(line + "\n")
            raw.flush()
            with lock:
                try:
                    handle(json.loads(line))
                except ValueError:
                    feed("system", line)
    code = p.wait()
    with lock:
        poll_hook_events()
        run.update(running=False, pid=None, exit_code=code, ended_at=now())
        final = "stopped" if run["stopping"] else "done"
        for agent, a in run["agents"].items():
            if a["status"] == "running":
                a["status"] = final
                a["since"] = now()
            instances[agent].clear()
        feed("main", "사용자가 중지함" if run["stopping"] else f"프로세스 종료 (코드 {code})")


def slugify(idea):
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", idea).strip("-")[:30] or "idea"
    return f"{s}-{datetime.now(KST):%m%d-%H%M}"


def start_run(idea):
    global proc, events_pos
    claude = shutil.which("claude")
    test_cmd = os.environ.get("DASHBOARD_CLAUDE_CMD")  # 테스트용 대체 명령(JSON 배열)
    if not claude and not test_cmd:
        raise RuntimeError("claude 명령을 찾을 수 없습니다.")
    if idea:
        folder = "ideas/" + slugify(idea)
        os.makedirs(os.path.join(ROOT, folder), exist_ok=True)
        prompt = PROMPT.format(idea=idea, folder=folder)
    else:
        folder = "."
        prompt = EXAMPLE_PROMPT
    os.makedirs(STATE_DIR, exist_ok=True)
    hook_cmd = f'"{sys.executable}" -I -X utf8 "{HOOK_PATH}"'
    settings = {"hooks": {ev: [{"hooks": [{"type": "command", "command": hook_cmd}]}]
                          for ev in ("SubagentStart", "SubagentStop")}}
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False)
    open(EVENTS_PATH, "w").close()
    open(STREAM_PATH, "w").close()
    events_pos = 0
    cmd = json.loads(test_cmd) if test_cmd else [
        claude, "-p", "--output-format", "stream-json", "--verbose",
        "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED_TOOLS,
        "--settings", SETTINGS_PATH,
    ]
    env = dict(os.environ, DASHBOARD_EVENTS=EVENTS_PATH)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    reset_run()
    p = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, env=env, creationflags=flags)
    p.stdin.write(prompt.encode("utf-8"))
    p.stdin.close()
    proc = p
    label = idea or "예시 모델(D마트 즉시배송)"
    run.update(running=True, pid=p.pid, idea=label, folder=folder, started_at=now())
    feed("main", f"실행 시작: {label}")
    threading.Thread(target=reader, args=(p,), daemon=True).start()
    return folder


def stop_run():
    if not run["running"] or not proc:
        return False
    run["stopping"] = True
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()
    return True


# ---------- 데이터 읽기 ----------

def safe_folder(rel):
    rel = (rel or ".").replace("\\", "/")
    path = os.path.realpath(os.path.join(ROOT, rel))
    if path != ROOT and not path.startswith(os.path.join(ROOT, "ideas") + os.sep):
        return None
    return path if os.path.isdir(path) else None


def list_folders():
    out = [{"value": ".", "label": "예시 모델 (D마트 즉시배송)"}]
    ideas = os.path.join(ROOT, "ideas")
    if os.path.isdir(ideas):
        for name in sorted(os.listdir(ideas), reverse=True):
            if os.path.isdir(os.path.join(ideas, name)):
                out.append({"value": f"ideas/{name}", "label": name})
    return out


def load_run_log(folder):
    path = os.path.join(folder, "run_log.json")
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (ValueError, OSError) as e:
        return None, f"run_log.json을 읽지 못했습니다: {e}"


_xlsx_cache = {}


def pnl_from_xlsx(folder):
    path = os.path.join(folder, EXAMPLE_MODEL if folder == ROOT else "model.xlsx")
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    if _xlsx_cache.get(path, (None,))[0] == mtime:
        return _xlsx_cache[path][1]
    result = None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        if "손익" in wb.sheetnames:
            rows = list(wb["손익"].iter_rows(values_only=True))
            header = next((r for r in rows if r and r[0] == "항목"), None)
            target = next((r for r in rows if r and r[0] == "월 영업손익"), None)
            if header and target:
                result = []
                for i, h in enumerate(header[1:], start=1):
                    if not h or "안" not in str(h) or not isinstance(target[i], (int, float)):
                        continue
                    plan, _, scenario = str(h).partition(" ")
                    result.append({"plan": plan, "scenario": scenario, "value": target[i],
                                   "cell": f"손익!{chr(65 + i)}{rows.index(target) + 1}"})
        wb.close()
    except Exception:
        result = None
    _xlsx_cache[path] = (mtime, result)
    return result


def build_state(rel):
    folder = safe_folder(rel)
    with lock:
        poll_hook_events()
        snapshot = json.loads(json.dumps(run))
    data = {"run": snapshot, "folders": list_folders(), "folder": rel,
            "log": None, "log_error": None, "pnl": None, "pnl_source": None,
            "findings": None, "conclusion": None}
    if not folder:
        data["log_error"] = "폴더를 찾을 수 없습니다."
        return data
    log, err = load_run_log(folder)
    data["log"], data["log_error"] = log, err
    entries = (log or {}).get("entries") or []
    pnl_entry = next((e for e in reversed(entries) if e.get("pnl")), None)
    if pnl_entry:
        data["pnl"], data["pnl_source"] = pnl_entry["pnl"], f"run_log #{pnl_entry.get('id')}"
    else:
        data["pnl"] = pnl_from_xlsx(folder)
        if data["pnl"]:
            data["pnl_source"] = "엑셀 캐시값 (손익 시트 월 영업손익)"
    review = next((e for e in reversed(entries) if e.get("findings") is not None), None)
    if review:
        data["findings"] = review["findings"]
    final = next((e for e in reversed(entries) if e.get("step") == 10), None)
    if final:
        data["conclusion"] = final.get("conclusion") or final.get("key_results")
    return data


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/dashboard.html"):
            with open(os.path.join(ROOT, "dashboard.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/state":
            self.send_json(build_state(parse_qs(url.query).get("folder", ["."])[0]))
        elif url.path == "/api/folders":
            self.send_json(list_folders())
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        # 다른 사이트가 localhost로 요청을 보내 실행시키는 것을 막는다
        origin = self.headers.get("Origin")
        allowed = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
        if self.headers.get("X-Dashboard") != "1" or (origin and origin not in allowed):
            return self.send_json({"error": "forbidden"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        path = urlparse(self.path).path
        with lock:
            if path == "/api/run":
                idea = str(body.get("idea") or "").strip()  # 비어 있으면 예시 모델 분석
                if run["running"]:
                    return self.send_json({"error": "이미 실행 중입니다."}, 409)
                try:
                    folder = start_run(idea)
                except Exception as e:
                    return self.send_json({"error": str(e)}, 500)
                return self.send_json({"ok": True, "folder": folder})
            if path == "/api/stop":
                return self.send_json({"ok": stop_run()})
        self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"대시보드: http://127.0.0.1:{PORT}  (종료: Ctrl+C)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
