"""관제 서버: 관제 화면 제공 + 실행 / 중지 버튼으로 에이전트 파이프라인 제어.

  python -I -X utf8 board/server.py            # http://127.0.0.1:8765 열기
  python -I -X utf8 board/server.py --port 9000 --no-open

파이프라인 (실행 버튼):
  0) 기존 part_*.csv · scorecard.md 백업 → board/runs/<시각>/backup
  1) review-tagger × 3 (묶음 1 · 2 · 3) 병렬 실행      — 단계 1 · 2 · 3 진행 중 표시
  2) 결과 확인 (각 part 100행)
  3) review-grader 채점 → ax/demo/scorecard.md        — 단계 5 진행 중 표시
중지 버튼: 실행 중인 claude 프로세스 트리를 모두 종료하고 백업으로 되돌린다.

각 에이전트는 `claude -p --agent <이름>` 으로 별도 프로세스에서 돈다 (.claude/agents/*.md 정의 사용).
127.0.0.1 에만 열리며, 한 번에 하나의 실행만 허용한다.
"""
import argparse, glob, http.server, json, os, shutil, subprocess, sys, threading, time, webbrowser

BOARD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BOARD)
import control  # noqa: E402  (같은 폴더의 관제 액션)

ROOT = control.ROOT
PARTS_DIR = control.PARTS_DIR
RUNS_DIR = os.path.join(BOARD, "runs")
CLAUDE = shutil.which("claude") or "claude"
BATCHES = [1, 2, 3]
TAGGER_TOOLS = "Read,Glob,Write,Edit"
GRADER_TOOLS = "Read,Glob,Grep,Write"


def child_env():
    """중첩 실행 차단 변수를 지운 환경 (서버를 Claude Code 안에서 띄워도 동작하게)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDECODE", "CLAUDE_CODE_"))}
    env["VOC_PROJECT_ROOT"] = ROOT
    return env


def tagger_prompt(n):
    batch = glob.glob(os.path.join(ROOT, "archive-*", "archive", f"batch{n}"))[0]
    pdef = glob.glob(os.path.join(ROOT, "painpoint-*", "painpoint", "painpoint_def.md"))[0]
    return (f"묶음 번호 N = {n}.\n리뷰 폴더: {batch}\n판정 기준: {pdef}\n"
            f"출력: {os.path.join(PARTS_DIR, f'part_{n}.csv')}\n"
            "에이전트 정의의 규칙대로 10건 읽을 때마다 즉시 10행을 추가 저장하고, 끝나면 태그별 건수를 한 줄로 보고해.\n"
            "중요: 이것은 관제 화면의 실행 버튼으로 시작된 비대화형 실행이라 답해 줄 사람이 없다. "
            "사용자에게 묻거나 선택지를 제시하지 말고 바로 처음부터 다시 분류한다. "
            "기존 part 파일이 있어도 기존 내용은 보지 말고, 첫 10건을 Write로 새로 써서 덮어쓴다 (백업은 관제 서버가 이미 했다).")


GRADER_PROMPT = (
    "ax/demo/parts/part_1.csv · part_2.csv · part_3.csv 를 원문과 대조해 채점하고 ax/demo/scorecard.md 를 새로 써. "
    "판정 기준은 painpoint_def.md 와 .claude/CLAUDE.md 의 '판정 보충 기준' 표. "
    "승인 행은 '사용자 위임 (2026-11-10)' · 결과 '완료(위임)' 로 적는다 (사용자가 승인을 위임함). "
    "비대화형 실행이므로 사용자에게 묻지 말고 바로 채점해 scorecard.md 를 덮어쓴다. "
    "끝나면 관제 화면 표만 보고해.")


class Pipeline:
    def __init__(self):
        self.lock = threading.Lock()
        self.procs = {}
        self.state = {"status": "idle", "phase": "", "started": None, "ended": None,
                      "agents": {}, "log": [], "run_dir": None, "message": "대기 중"}
        self.stop_flag = threading.Event()

    # ── 상태 ──
    def log(self, msg):
        line = time.strftime("%H:%M:%S ") + msg
        with self.lock:
            self.state["log"] = (self.state["log"] + [line])[-80:]
        if self.state.get("run_dir"):
            with open(os.path.join(self.state["run_dir"], "run.log"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        print(line, flush=True)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def agent(self, name, **kw):
        with self.lock:
            self.state["agents"].setdefault(name, {}).update(kw)

    # ── 제어 ──
    def start(self):
        with self.lock:
            if self.state["status"] == "running":
                return False, "이미 실행 중입니다."
            run_dir = os.path.join(RUNS_DIR, time.strftime("%Y%m%d-%H%M%S"))
            self.state = {"status": "running", "phase": "백업", "started": int(time.time()), "ended": None,
                          "agents": {}, "log": [], "run_dir": run_dir, "message": "실행 시작"}
        self.stop_flag.clear()
        threading.Thread(target=self._run, daemon=True).start()
        return True, "실행을 시작했습니다."

    def stop(self):
        if self.state["status"] != "running":
            return False, "실행 중이 아닙니다."
        self.stop_flag.set()
        self.set(phase="중지 중", message="중지 요청됨")
        self.log("■ 중지 요청 — 프로세스 종료")
        for name, p in list(self.procs.items()):
            kill_tree(p)
            self.agent(name, status="stopped")
        return True, "중지했습니다."

    # ── 실행 ──
    def _spawn(self, name, agent, prompt, tools):
        log_path = os.path.join(self.state["run_dir"], f"{name}.log")
        out = open(log_path, "w", encoding="utf-8")
        cmd = [CLAUDE, "-p", prompt, "--agent", agent, "--permission-mode", "acceptEdits",
               "--allowedTools", tools, "--no-session-persistence"]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        p = subprocess.Popen(cmd, cwd=ROOT, env=child_env(), stdout=out, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, creationflags=flags)
        self.procs[name] = p
        self.agent(name, status="running", pid=p.pid, started=int(time.time()), agent=agent, log=os.path.relpath(log_path, BOARD))
        self.log(f"▶ {name} 시작 ({agent}, pid {p.pid})")
        return p, out

    def _wait_all(self, running):
        while running:
            for name, (p, out) in list(running.items()):
                rc = p.poll()
                if rc is not None:
                    out.close()
                    last = tail(os.path.join(self.state["run_dir"], f"{name}.log"))
                    st = "stopped" if self.stop_flag.is_set() else ("done" if rc == 0 else "error")
                    self.agent(name, status=st, rc=rc, ended=int(time.time()), result=last)
                    self.log(f"{'✔' if st == 'done' else '✖'} {name} 종료 (code {rc}) {last}")
                    running.pop(name)
                    self.procs.pop(name, None)
            time.sleep(0.5)

    def _run(self):
        rd = self.state["run_dir"]
        os.makedirs(os.path.join(rd, "backup"), exist_ok=True)
        try:
            # 0) 백업
            for f in glob.glob(os.path.join(PARTS_DIR, "part_*.csv")) + [control.SCORECARD]:
                if os.path.exists(f):
                    shutil.copy2(f, os.path.join(rd, "backup", os.path.basename(f)))
            self.log(f"백업 완료 → {os.path.relpath(rd, ROOT)}\\backup")
            if self.stop_flag.is_set():
                return self._abort()

            # 1) 분류
            self.set(phase="분류 (review-tagger × 3)")
            for st in (1, 2, 3):
                control.mark_stage(st, "start", "관제 실행: review-tagger 분류")
            running = {f"tagger-{n}": self._spawn(f"tagger-{n}", "review-tagger", tagger_prompt(n), TAGGER_TOOLS)
                       for n in BATCHES}
            self._wait_all(running)
            for st in (1, 2, 3):
                control.mark_stage(st, "end", "")
            if self.stop_flag.is_set():
                return self._abort()

            # 2) 결과 확인
            short = [n for n in BATCHES if part_rows(n) != 100]
            if short:
                self.log(f"✖ 분류 결과 행 수 부족: part {short}")
                return self._abort("분류 실패")

            # 3) 채점
            self.set(phase="채점 (review-grader)")
            control.mark_stage(5, "start", "관제 실행: review-grader 채점")
            running = {"grader": self._spawn("grader", "review-grader", GRADER_PROMPT, GRADER_TOOLS)}
            self._wait_all(running)
            control.mark_stage(5, "end", "")
            if self.stop_flag.is_set():
                return self._abort()

            refresh()
            self.set(status="done", phase="완료", ended=int(time.time()), message="파이프라인 완료")
            self.log("■ 완료")
        except Exception as e:  # 예외도 화면에 보이게
            self.log(f"✖ 오류: {e}")
            self._abort("오류")

    def _abort(self, why="사용자 중지"):
        for st in (1, 2, 3, 5):
            control.mark_stage(st, "end", why)
        restored = []
        bdir = os.path.join(self.state["run_dir"], "backup")
        for f in glob.glob(os.path.join(bdir, "*")):
            dest = control.SCORECARD if os.path.basename(f) == "scorecard.md" else os.path.join(PARTS_DIR, os.path.basename(f))
            shutil.copy2(f, dest)
            restored.append(os.path.basename(f))
        self.log(f"↺ 백업으로 복원: {', '.join(restored) or '없음'}")
        refresh()
        self.set(status="stopped" if why == "사용자 중지" else "error", phase=why, ended=int(time.time()), message=f"{why} · 백업 복원")


def kill_tree(p):
    if p.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()


def tail(path, n=160):
    try:
        txt = open(path, encoding="utf-8", errors="replace").read().strip()
        return txt.splitlines()[-1][:n] if txt else ""
    except OSError:
        return ""


def part_rows(n):
    p = os.path.join(PARTS_DIR, f"part_{n}.csv")
    if not os.path.exists(p):
        return 0
    return max(0, sum(1 for line in open(p, encoding="utf-8-sig") if line.strip()) - 1)


PIPE = Pipeline()


def refresh():
    st = control.run()
    st["pipeline"] = PIPE.snapshot()
    st["server"] = True
    control.save(st)
    return st


def monitor_loop(interval):
    while True:
        try:
            refresh()
        except Exception as e:
            print("monitor:", e, file=sys.stderr)
        time.sleep(interval)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BOARD, **kw)

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if self.path.startswith("/status"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/api/state"):
            return self._json(200, PIPE.snapshot())
        return super().do_GET()

    def do_POST(self):
        host = self.headers.get("Host", "")
        if not host.startswith(("127.0.0.1", "localhost")):
            return self._json(403, {"ok": False, "msg": "로컬에서만 허용"})
        if self.path == "/api/run":
            ok, msg = PIPE.start()
        elif self.path == "/api/stop":
            ok, msg = PIPE.stop()
        else:
            return self._json(404, {"ok": False, "msg": "없는 경로"})
        refresh()
        return self._json(200 if ok else 409, {"ok": ok, "msg": msg, "state": PIPE.snapshot()})


def main():
    ap = argparse.ArgumentParser(description="VOC 관제 서버")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--interval", type=float, default=2.0, help="관제 점검 간격(초)")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    os.makedirs(RUNS_DIR, exist_ok=True)
    refresh()
    threading.Thread(target=monitor_loop, args=(a.interval,), daemon=True).start()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"관제 서버 {url}  (claude: {CLAUDE})  Ctrl+C 종료", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        PIPE.stop()
        srv.shutdown()


if __name__ == "__main__":
    main()
