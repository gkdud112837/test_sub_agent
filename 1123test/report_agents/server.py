"""로컬 전용 웹 서버 (표준 라이브러리 http.server).

- 127.0.0.1/localhost에만 바인딩하고, Host 헤더도 로컬 주소만 받는다.
- 화면 파일은 web/, 실행 결과는 workspace/run-*/ 에서 읽는다.

GET  /                      web/index.html
GET  /web/<파일>             화면 정적 파일
GET  /api/config            페이즈·에이전트 구성, 모델, 키 준비 여부
GET  /api/state?since=N     실행 상태, 에이전트 상태, 이벤트(N번째부터)
POST /api/run               {"dry_run": bool, "use_search": bool} 실행 시작
GET  /api/runs              실행 목록
GET  /api/files?run=ID      실행 폴더 파일 목록
GET  /api/file?run=ID&path= 파일 내용
GET  /api/report?run=ID     최종 리포트 HTML
"""

import asyncio
import json
import mimetypes
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import markdown

from .config import ROOT, Settings, load_settings
from .runner import build
from .specs import Specs
from .workspace import now_kst

WEB_DIR = ROOT / "web"
RUN_ID = re.compile(r"^run-[0-9\-]+$")


class RunState:
    """실행 하나의 상태. 오케스트레이터 스레드가 emit으로 채우고, HTTP 스레드가 읽는다."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.run_id: str | None = None
        self.mode = ""
        self.started_at = self.finished_at = None
        self.error: str | None = None
        self.final: str | None = None
        self.events: list[dict] = []
        self.agents: dict[str, dict] = {}

    def reset(self, run_id: str, mode: str) -> None:
        with self.lock:
            self.running, self.run_id, self.mode = True, run_id, mode
            self.started_at, self.finished_at = now_kst(), None
            self.error = self.final = None
            self.events, self.agents = [], {}

    def emit(self, e: dict) -> None:
        with self.lock:
            e = {"t": now_kst(), **e}
            self.events.append(e)
            agent = e.get("agent")
            if not agent:
                return
            key = f"{agent}@{e['phase']}" if agent == "main" else agent
            a = self.agents.setdefault(key, {"status": "waiting", "runs": 0, "routes": []})
            if e["type"] == "start":
                a["status"] = "running"
                a["runs"] += 1
                if e.get("route"):
                    a["routes"].append(e["route"])
            else:
                a["status"] = "done" if e["type"] == "done" else "failed"
                a["summary"] = e.get("summary", "")

    def finish(self, *, final: str | None = None, error: str | None = None) -> None:
        with self.lock:
            self.running = False
            self.finished_at = now_kst()
            self.final, self.error = final, error

    def snapshot(self, since: int) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "run_id": self.run_id,
                "mode": self.mode,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "final": self.final,
                "agents": self.agents,
                "events": self.events[since:],
                "n_events": len(self.events),
            }


def _safe_md(text: str) -> str:
    """LLM이 쓴 마크다운 속 HTML은 막고, 우리가 넣는 <sub>만 살린다."""
    text = text.replace("<", "&lt;")
    text = re.sub(r"&lt;(/?)sub>", r"<\1sub>", text)
    text = re.sub(r"&lt;!--.*?-->", "", text, flags=re.S)
    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])


class App:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.specs = Specs(settings.config_dir)
        self.state = RunState()

    def run_dir(self, run_id: str) -> Path | None:
        if not run_id or not RUN_ID.match(run_id):
            return None
        p = self.settings.workspace_dir / run_id
        return p if p.is_dir() else None

    def start(self, dry_run: bool, use_search: bool) -> tuple[int, dict]:
        if self.state.running:
            return 409, {"error": "이미 실행 중입니다."}
        if not dry_run and not self.settings.api_key_ready:
            return 400, {"error": ".env의 GEMINI_API_KEY가 비어 있습니다. dry-run으로 실행하거나 키를 넣고 서버를 다시 켜세요."}
        try:
            run_id, orch = build(
                self.settings, dry_run=dry_run, use_search=use_search, say=print, emit=self.state.emit
            )
        except Exception as e:
            return 400, {"error": str(e)}
        self.state.reset(run_id, "dry-run" if dry_run else self.settings.model)

        def work():
            try:
                path = asyncio.run(orch.run())
                self.state.finish(final=path.relative_to(self.settings.workspace_dir / run_id).as_posix())
            except Exception as e:
                traceback.print_exc()
                self.state.emit({"type": "log", "msg": f"실행 중단: {type(e).__name__}: {e}"})
                self.state.finish(error=f"{type(e).__name__}: {e}")

        threading.Thread(target=work, daemon=True, name=run_id).start()
        return 200, {"run_id": run_id}

    def config(self) -> dict:
        sp, s = self.specs, self.settings
        agents = {sp.main: {"label": sp.raw["main"]["label"], "role": sp.raw["main"]["role"]}}
        for a in sp.analysts.values():
            agents[a.name] = {"label": a.label, "role": f"{a.section} ({a.pages})"}
        for a in (sp.writer, sp.charter, *sp.reviewers):
            agents[a["name"]] = {"label": a["label"], "role": a["label"]}
        return {
            "phases": sp.raw["phases"],
            "agents": agents,
            "dirs": sp.dirs,
            "model": s.model,
            "api_key_ready": s.api_key_ready,
            "use_search": s.use_search,
            "max_rework": s.max_rework,
        }


def make_handler(app: App):
    allowed_hosts = {f"127.0.0.1:{app.settings.web_port}", f"localhost:{app.settings.web_port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 폴링 요청 로그는 끈다
            pass

        def _local_only(self) -> bool:
            if self.headers.get("Host") not in allowed_hosts:
                self._send(403, {"error": "로컬 전용 서비스입니다."})
                return False
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc not in allowed_hosts:
                self._send(403, {"error": "로컬 전용 서비스입니다."})
                return False
            return True

        def _send(self, code: int, body, ctype: str = "application/json; charset=utf-8") -> None:
            data = body if isinstance(body, bytes) else (
                json.dumps(body, ensure_ascii=False).encode() if not isinstance(body, str) else body.encode()
            )
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _static(self, path: Path) -> None:
            if not path.is_file():
                return self._send(404, {"error": "없음"})
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, path.read_bytes(), ctype)

        def do_GET(self):
            if not self._local_only():
                return
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            p = url.path
            if p == "/":
                return self._static(WEB_DIR / "index.html")
            if p.startswith("/web/"):
                target = (WEB_DIR / p[len("/web/"):]).resolve()
                if not target.is_relative_to(WEB_DIR.resolve()):
                    return self._send(403, {"error": "금지"})
                return self._static(target)
            if p == "/api/config":
                return self._send(200, app.config())
            if p == "/api/state":
                return self._send(200, app.state.snapshot(int(q.get("since", 0))))
            if p == "/api/runs":
                root = app.settings.workspace_dir
                runs = sorted((d.name for d in root.glob("run-*") if d.is_dir()), reverse=True) if root.exists() else []
                return self._send(200, {"runs": runs})

            run = app.run_dir(q.get("run", ""))
            if p.startswith("/api/") and run is None:
                return self._send(404, {"error": "실행을 찾을 수 없습니다."})
            if p == "/api/files":
                files = [
                    {"path": f.relative_to(run).as_posix(), "size": f.stat().st_size}
                    for f in sorted(run.rglob("*")) if f.is_file() and not f.name.endswith(".tmp")
                ]
                return self._send(200, {"files": files})
            if p == "/api/file":
                target = (run / q.get("path", "")).resolve()
                if not target.is_relative_to(run.resolve()):
                    return self._send(403, {"error": "금지"})
                if not target.is_file():
                    return self._send(404, {"error": "없음"})
                if target.suffix.lower() == ".png":
                    return self._send(200, target.read_bytes(), "image/png")
                # 그 밖의 결과 파일은 항상 글자로만 보여준다 (HTML로 해석하지 않음)
                return self._send(200, target.read_bytes(), "text/plain; charset=utf-8")
            if p == "/api/report":
                final_dir = app.specs.dirs["final"]
                md_path = run / final_dir / "report.md"
                if not md_path.is_file():
                    return self._send(404, {"error": "아직 최종 리포트가 없습니다."})
                html = _safe_md(md_path.read_text(encoding="utf-8"))
                html = re.sub(
                    r'src="charts/([a-z0-9\-]+\.png)"',
                    lambda m: f'src="/api/file?run={run.name}&path={final_dir}/charts/{m.group(1)}"',
                    html,
                )
                return self._send(200, {"html": html})
            return self._send(404, {"error": "없음"})

        def do_POST(self):
            if not self._local_only():
                return
            if urlparse(self.path).path != "/api/run":
                return self._send(404, {"error": "없음"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "JSON 형식이 아닙니다."})
            code, out = app.start(bool(body.get("dry_run")), bool(body.get("use_search")))
            return self._send(code, out)

    return Handler


def serve() -> None:
    settings = load_settings()
    app = App(settings)
    server = ThreadingHTTPServer((settings.web_host, settings.web_port), make_handler(app))
    print(f"로컬 전용 서버: http://{settings.web_host}:{settings.web_port}  (종료: Ctrl+C)")
    print(f"모델 {settings.model} · API 키 {'있음' if settings.api_key_ready else '없음 (dry-run만 가능)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
