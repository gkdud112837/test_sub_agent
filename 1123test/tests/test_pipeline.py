"""가짜 LLM(fixtures/dry_run.json)으로 전체 흐름을 확인한다. API 키 불필요."""

import asyncio
import json
from pathlib import Path

import pytest

from report_agents.config import ROOT, ConfigError, load_settings
from report_agents.fake_llm import FakeLLM
from report_agents.orchestrator import Orchestrator, normalize_issue
from report_agents.server import _safe_md
from report_agents.specs import Specs
from report_agents.workspace import Workspace

SPECS = Specs(ROOT / "config")


@pytest.fixture
def result(tmp_path):
    llm = FakeLLM(ROOT / "fixtures" / "dry_run.json", SPECS, delay=0.05)
    events = []
    orch = Orchestrator(
        llm,
        Workspace(tmp_path / "ws"),
        SPECS,
        brief_path=ROOT / "data" / "brief.md",
        reference_pdf=ROOT / "IT하드웨어_SK증권_산업리포트.pdf",
        max_rework=2,
        use_search=True,
        say=lambda m: None,
        emit=events.append,
    )
    final = asyncio.run(orch.run())
    return {"ws": tmp_path / "ws", "final": final, "llm": llm, "events": events, "orch": orch}


def test_analysts_run_in_parallel(result):
    # P1 분석 5개가 동시에 떠 있어야 한다
    assert result["llm"].peak >= len(SPECS.analyst_names)


def test_all_routes_happen(result):
    log = json.loads((result["ws"] / "run_log.json").read_text(encoding="utf-8"))
    routes = {e["route"] for e in log["entries"] if e["route"]}
    assert {"R1", "R2", "R3", "R4", "R5"} <= routes
    # 다시 돈 기록은 이전 기록을 가리킨다
    rerun = [e for e in log["entries"] if e["agent"] == "inflation-analyst" and e["route"] == "R3"]
    assert rerun and rerun[0]["rerun_of"] is not None


def test_results_are_files_in_workspace(result):
    ws = result["ws"]
    for name in SPECS.analyst_names:
        for f in ("section.md", "data.csv", "sources.md", "handoff.md", "research.md"):
            assert (ws / "10_analysis" / name / f).is_file(), f"{name}/{f}"
    for rel in ("00_brief/brief.md", "20_draft/report.md", "20_draft/questions.md",
                "30_review/facts.md", "30_review/logic.md", "40_final/report.md"):
        assert (ws / rel).is_file(), rel
    # 다시 쓴 파일은 이전 판이 _v1로 남는다
    assert (ws / "10_analysis/inflation-analyst/section_v1.md").is_file()
    assert (ws / "20_draft/report_v1.md").is_file()


def test_r5_decision_written_to_brief(result):
    brief = (result["ws"] / "00_brief/brief.md").read_text(encoding="utf-8")
    assert SPECS.txt("r5_header") in brief
    assert "LTA 선수금" in brief


def test_final_report(result):
    final = result["final"].read_text(encoding="utf-8")
    assert "<!-- section:" not in final  # 차트 자리가 모두 채워짐
    assert "charts/demand-yoy.png" in final and "charts/inflation-cost.png" in final
    assert (result["ws"] / "40_final/charts/demand-yoy.png").is_file()
    assert "[확인필요] 목록" in final and "LTA 선수금" in final
    # 길이가 안 맞는 차트는 그리지 않고 기록만 남긴다
    assert "broken" in (result["ws"] / "20_draft/charts/index_v1.md").read_text(encoding="utf-8")


def test_events_for_web(result):
    types = {e["type"] for e in result["events"]}
    assert {"start", "done", "log"} <= types


def test_issue_route_follows_target():
    i = normalize_issue({"route": "R1", "target": "lta-analyst", "severity": "blocker"}, "fact-checker", SPECS)
    assert i.route == "R3"
    i = normalize_issue({"route": "R3", "target": "unknown"}, "logic-reviewer", SPECS)
    assert (i.route, i.target) == ("R1", "report-writer")


def test_schema_enums_filled_from_config():
    s = SPECS.schema("review")
    targets = s["properties"]["issues"]["items"]["properties"]["target"]["enum"]
    assert targets[:2] == ["report-writer", "chart-maker"] and "lta-analyst" in targets


def test_web_host_must_be_local(tmp_path, monkeypatch):
    env = (ROOT / ".env.example").read_text(encoding="utf-8").replace("WEB_HOST=127.0.0.1", "WEB_HOST=0.0.0.0")
    f = tmp_path / ".env"
    f.write_text(env, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(f)
    monkeypatch.setenv("WEB_HOST", "127.0.0.1")


def test_markdown_blocks_raw_html():
    html = _safe_md("# 제목\n\n<script>alert(1)</script>\n\n<sub>자료: X</sub>\n\n> 인용")
    assert "<script>" not in html and "<sub>자료: X</sub>" in html and "<blockquote>" in html
