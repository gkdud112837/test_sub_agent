"""CLI와 웹 서버가 같이 쓰는 실행 준비 코드. 실행마다 workspace/run-YYYYMMDD-HHMMSS/를 새로 만든다."""

from datetime import datetime
from typing import Callable

from .config import Settings
from .fake_llm import FakeLLM
from .llm import GeminiLLM
from .orchestrator import Orchestrator
from .specs import Specs
from .workspace import KST, Workspace


def new_run_id(settings: Settings) -> str:
    base = datetime.now(KST).strftime("run-%Y%m%d-%H%M%S")
    run_id, n = base, 1
    while (settings.workspace_dir / run_id).exists():
        n += 1
        run_id = f"{base}-{n}"
    return run_id


def build(
    settings: Settings,
    *,
    dry_run: bool,
    use_search: bool | None = None,
    say: Callable[[str], None] = print,
    emit: Callable[[dict], None] = lambda e: None,
) -> tuple[str, Orchestrator]:
    specs = Specs(settings.config_dir)
    llm = FakeLLM(settings.dry_run_fixture, specs) if dry_run else GeminiLLM(settings, specs.msg("json_retry"))
    run_id = new_run_id(settings)
    orch = Orchestrator(
        llm,
        Workspace(settings.workspace_dir / run_id),
        specs,
        brief_path=settings.brief_path,
        reference_pdf=settings.reference_pdf,
        max_rework=settings.max_rework,
        use_search=settings.use_search if use_search is None else use_search,
        say=say,
        emit=emit,
    )
    return run_id, orch
