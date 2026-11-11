"""레드팀 모니터 서버 — 수업 예시

실행:  python monitor/server.py   →  http://localhost:8765

- [실행] : redteam-investor / redteam-customer / redteam-competitor 를 `claude -p --agent` 로 동시에 실행 (읽기 도구만 허용)
- 결과 원문은 bm/redteam/runs/<실행id>/<에이전트>.md 에 그대로 저장
- 지적은 bm/redteam_log.md 에 실행별 표로 합침
- [수용]  → 결정 "반영" : 레드팀 제안을 캔버스에 반영
  [수정]  → 결정 "반영" : 사람이 고친 내용을 캔버스에 반영
  [반려]  → 결정 "반박" : 캔버스는 고치지 않음
- 캔버스 반영은 Claude(읽기 전용)가 수정안(JSON)을 만들고, 서버가 원문 일치를 확인한 뒤 적용한다.
"""
import datetime
import json
import re
import shutil
import subprocess
import threading
import queue
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 8765
ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
BM = ROOT / "bm"
RUNS = BM / "redteam" / "runs"
LOG_MD = BM / "redteam_log.md"
CANVAS = BM / "bm_canvas.md"
CLAUDE = shutil.which("claude")
TIMEOUT = 900  # 초

AGENTS = [
    ("redteam-investor", "투자자", "INV"),
    ("redteam-customer", "고객", "CUS"),
    ("redteam-competitor", "경쟁자", "COM"),
]
MATERIALS = (
    "painpoint/painpoint_def.md, ax/jtbd.md, ax/opportunity_matrix.csv, ax/risk_check.md, "
    "ax/ideas_top3.md, research/data/sources.md, valuechain/valuechain_v1.md, "
    "bm/survey_merchant_assoc.md, bm/revenue_options.md"
)
READ_ONLY = ["--allowedTools", "Read", "Glob", "Grep",
             "--disallowedTools", "Edit", "Write", "Bash", "NotebookEdit", "PowerShell"]

lock = threading.RLock()
apply_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
STATE: dict = {"run": None}


def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_dir() -> Path:
    return RUNS / STATE["run"]["id"]


def event(msg: str, level: str = "info") -> None:
    with lock:
        run = STATE["run"]
        e = {"t": now(), "msg": msg, "level": level}
        run["events"].append(e)
        with open(run_dir() / "events.log", "a", encoding="utf-8") as f:
            f.write(f"[{e['t']}] {level.upper():5} {msg}\n")


def save() -> None:
    with lock:
        run = STATE["run"]
        (run_dir() / "state.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        write_log_md(run)


# ---------------------------------------------------------------- redteam_log.md
def cell(s: str) -> str:
    return (s or "").replace("|", "／").replace("\r", " ").replace("\n", " ").strip()


def write_log_md(run: dict) -> None:
    rid = run["id"]
    start, end = f"<!-- monitor-run:{rid} start -->", f"<!-- monitor-run:{rid} end -->"
    lines = [
        start,
        f"## 모니터 실행 {rid}",
        "",
        f"- 실행: {run['started']} · 레드팀 3개 동시 실행(읽기 전용) · 모니터(`monitor/monitor.html`)",
        f"- 원문: `bm/redteam/runs/{rid}/` (에이전트별 .md · events.log · state.json)",
        "- 결정 주체: 사람(모니터 버튼). 수용 → `반영` · 수정 → `반영`(사람 수정안) · 반려 → `반박`",
        "",
        "| id | 레드팀 | 대상 칸 | 지적 | 근거 | 결정 | 결정 이유 | 캔버스 수정 내용 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for it in run["items"]:
        st = it["status"]
        if st == "pending":
            dec, why, chg = "", "", ""
        elif st in ("queued", "applying"):
            dec, why, chg = "반영(적용 중)", it.get("reason", ""), "적용 중"
        elif st == "error":
            dec, why, chg = "반영(적용 실패)", it.get("reason", ""), "적용 실패 — " + it.get("error", "")
        else:
            dec, why, chg = it["decision"], it.get("reason", ""), it.get("change", "")
        lines.append("| " + " | ".join(cell(x) for x in [
            it["id"], it["agent"], it["cell"], f"[{it['severity']}] {it['issue']}", it["basis"], dec, why, chg]) + " |")
    total = len(run["items"])
    done = sum(1 for it in run["items"] if it["status"] == "done")
    lines += ["", f"- 결정 완료 {done}건(확인값 · 이 로그) / {total}건(확인값 · 이 로그)", end]
    block = "\n".join(lines)

    text = LOG_MD.read_text(encoding="utf-8") if LOG_MD.exists() else "# 레드팀 로그\n"
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    text = pat.sub(lambda _: block, text) if pat.search(text) else text.rstrip() + "\n\n---\n\n" + block + "\n"
    LOG_MD.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- claude 호출
def call_claude(args: list[str], prompt: str) -> str:
    if not CLAUDE:
        raise RuntimeError("claude CLI 를 찾을 수 없음")
    p = subprocess.run([CLAUDE, "-p", *args, "--output-format", "text"], input=prompt,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=ROOT, timeout=TIMEOUT)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or f"exit {p.returncode}").strip()[:400])
    return p.stdout


def parse_items(raw: str, agent: str, label: str) -> list[dict]:
    items = []
    for line in raw.splitlines():
        s = line.strip()
        if not re.match(r"^\|\s*(INV|CUS|COM)-\d+", s):
            continue
        c = [x.strip() for x in s.strip("|").split("|")]
        if len(c) < 6:
            continue
        items.append({
            "key": f"{agent}:{c[0]}", "id": c[0], "agent": agent, "label": label,
            "cell": c[1], "issue": c[2], "basis": c[3], "severity": c[4], "suggestion": " | ".join(c[5:]),
            "status": "pending", "decision": "", "action": "", "reason": "", "change": "", "text": "",
        })
    return items


def run_agent(name: str, label: str) -> None:
    a = STATE["run"]["agents"][name]
    with lock:
        a.update(status="running", started=now())
    event(f"{label} 레드팀({name}) 시작")
    save()
    prompt = (
        f'너는 레드팀 서브에이전트 "{name}" 역할이다. 작업 폴더는 현재 폴더다.\n'
        "1. CLAUDE.md 를 읽는다.\n"
        f"2. bm/bm_canvas.md 를 재료 파일({MATERIALS})과 대조해 너의 관점에서 검증한다. 끝까지 읽는다.\n"
        "파일은 읽기만 한다. 최종 답은 너의 에이전트 정의에 있는 출력 형식(제목 + 표)만, 다른 설명 없이 돌려준다."
    )
    try:
        raw = call_claude(["--agent", name, *READ_ONLY], prompt)
        (run_dir() / f"{name}.md").write_text(raw, encoding="utf-8")
        items = parse_items(raw, name, label)
        with lock:
            STATE["run"]["items"].extend(items)
            a.update(status="done", finished=now(), count=len(items))
        event(f"{label} 레드팀 검토 완료 — 지적 {len(items)}건 · 원문 bm/redteam/runs/{STATE['run']['id']}/{name}.md", "done")
        if not items:
            event(f"{label} 레드팀 결과에서 표를 찾지 못함 — 원문 파일 확인 필요", "warn")
    except Exception as e:  # noqa: BLE001
        with lock:
            a.update(status="error", finished=now(), error=str(e))
        event(f"{label} 레드팀 실패: {e}", "error")
    save()
    with lock:
        if all(x["status"] in ("done", "error") for x in STATE["run"]["agents"].values()):
            STATE["run"]["status"] = "done"
            n = len(STATE["run"]["items"])
            event(f"레드팀 3개 검토 종료 — 사람 결정이 필요한 지적 {n}건", "done")
            save()


def start_run() -> dict:
    with lock:
        if STATE["run"] and STATE["run"]["status"] == "running":
            raise RuntimeError("이미 실행 중")
        rid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        STATE["run"] = {
            "id": rid, "started": now(), "status": "running", "events": [], "items": [],
            "agents": {n: {"name": n, "label": l, "status": "queued", "started": None, "finished": None,
                           "count": 0, "error": ""} for n, l, _ in AGENTS},
        }
        run_dir().mkdir(parents=True, exist_ok=True)
    event("실행 버튼 — 레드팀 3개 동시 실행")
    save()
    for n, l, _ in AGENTS:
        threading.Thread(target=run_agent, args=(n, l), daemon=True).start()
    return STATE["run"]


# ---------------------------------------------------------------- 결정 · 캔버스 반영
def find_item(key: str) -> dict:
    for it in STATE["run"]["items"]:
        if it["key"] == key:
            return it
    raise KeyError(key)


def decide(key: str, action: str, text: str) -> None:
    with lock:
        it = find_item(key)
        if it["status"] in ("queued", "applying", "done"):
            raise RuntimeError("이미 결정된 항목")
        it["action"] = action
        if action == "reject":
            it.update(status="done", decision="반박",
                      reason="사람 반려" + (f": {text}" if text.strip() else ""), change="수정 없음")
            event(f"{it['id']} 반려 → 반박 · 캔버스 수정 없음")
        elif action in ("accept", "modify"):
            if action == "modify" and not text.strip():
                raise RuntimeError("수정 내용이 비어 있음")
            body = it["suggestion"] if action == "accept" else text.strip()
            it.update(status="queued", decision="반영", text=body, error="",
                      reason="사람 수용(레드팀 제안 그대로)" if action == "accept" else f"사람 수정: {body}")
            event(f"{it['id']} {'수용' if action == 'accept' else '수정'} → 반영 · 캔버스 적용 대기")
            apply_q.put((STATE["run"]["id"], key))
        else:
            raise RuntimeError("알 수 없는 동작")
    save()


def extract_json(s: str) -> dict:
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("JSON 없음")
    return json.loads(s[a:b + 1])


def apply_worker() -> None:
    while True:
        rid, key = apply_q.get()
        try:
            with lock:
                if not STATE["run"] or STATE["run"]["id"] != rid:
                    continue
                it = find_item(key)
                it["status"] = "applying"
            event(f"{it['id']} 캔버스 수정안 생성 중")
            save()
            prompt = (
                "BM 캔버스 수정안을 만드는 작업이다. 먼저 CLAUDE.md 와 bm/bm_canvas.md 를 끝까지 읽어라. "
                "근거 확인이 필요하면 재료 파일도 읽어라. 파일은 고치지 말고 읽기만 한다.\n\n"
                f"사람이 아래 레드팀 지적을 '{'수용' if it['action'] == 'accept' else '수정'}'했다. "
                "'반영할 내용'을 bm/bm_canvas.md 에 넣기 위한 최소한의 수정안을 만들어라.\n"
                f"- 지적 id: {it['id']} ({it['label']} 레드팀)\n- 대상 칸: {it['cell']}\n"
                f"- 지적: {it['issue']}\n- 반영할 내용: {it['text']}\n\n"
                "규칙: CLAUDE.md 규칙 1·2·4 를 지킨다. 칸 끝의 근거 줄을 유지 · 갱신한다. 새로 넣는 모든 숫자에 "
                "(가정값) 또는 (확인값 · 출처파일)을 붙인다. 재료에 없는 사실 · 금액 · 기관명을 지어내지 않는다(없으면 미확인). "
                "후보는 나열만 하고 고르지 않는다. 대상 칸 안에서만 고친다.\n\n"
                "출력은 아래 JSON 하나만, 다른 글 없이:\n"
                '{"summary":"캔버스에서 무엇을 바꿨는지 한 줄","edits":[{"old":"bm/bm_canvas.md 에 그대로 있는 원문(파일 안에서 한 번만 나와야 함)","new":"바꿀 내용"}]}'
            )
            out = call_claude(READ_ONLY, prompt)
            data = extract_json(out)
            edits = data.get("edits") or []
            if not edits:
                raise ValueError("수정안이 비어 있음")
            with lock:
                text = CANVAS.read_text(encoding="utf-8")
                for e in edits:
                    n = text.count(e["old"])
                    if n != 1:
                        raise ValueError(f"원문 일치 {n}회 — 적용 중단: {e['old'][:40]}…")
                    text = text.replace(e["old"], e["new"], 1)
                CANVAS.write_text(text, encoding="utf-8")
                it.update(status="done", change=data.get("summary", "").strip() or "캔버스 수정")
            event(f"{it['id']} 캔버스 반영 완료 — {it['change']}", "done")
        except Exception as e:  # noqa: BLE001
            with lock:
                it = find_item(key)
                it.update(status="error", error=str(e)[:300])
            event(f"{it['id']} 캔버스 반영 실패: {e} — 다시 결정할 수 있음", "error")
        finally:
            save()
            apply_q.task_done()


def load_latest() -> None:
    if not RUNS.exists():
        return
    runs = sorted([p for p in RUNS.iterdir() if (p / "state.json").exists()])
    if not runs:
        return
    run = json.loads((runs[-1] / "state.json").read_text(encoding="utf-8"))
    for a in run["agents"].values():  # 서버가 꺼진 동안 끊긴 실행
        if a["status"] in ("running", "queued"):
            a.update(status="error", error="서버 재시작으로 중단")
    for it in run["items"]:
        if it["status"] in ("queued", "applying"):
            it.update(status="error", error="서버 재시작으로 중단")
    if run["status"] == "running":
        run["status"] = "done"
    STATE["run"] = run


# ---------------------------------------------------------------- HTTP
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 콘솔 조용히
        pass

    def send(self, code: int, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/monitor.html"):
            return self.send(200, (HERE / "monitor.html").read_bytes(), "text/html; charset=utf-8")
        if self.path.startswith("/api/status"):
            with lock:
                return self.send(200, {"run": STATE["run"], "claude": bool(CLAUDE), "queue": apply_q.qsize()})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/run":
                start_run()
            elif self.path == "/api/decide":
                decide(body["key"], body["action"], body.get("text", ""))
            else:
                return self.send(404, {"error": "not found"})
            self.send(200, {"ok": True})
        except Exception as e:  # noqa: BLE001
            self.send(400, {"error": str(e)})


if __name__ == "__main__":
    load_latest()
    threading.Thread(target=apply_worker, daemon=True).start()
    print(f"레드팀 모니터: http://localhost:{PORT}   (claude: {CLAUDE or '없음'})")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
