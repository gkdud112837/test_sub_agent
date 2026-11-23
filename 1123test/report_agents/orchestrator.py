"""메인 세션(오케스트레이터).

LLM 에이전트가 아니라 파이썬 코드다. 범위는 사람이 쓴 brief를 그대로 쓰고(P0),
P1~P3의 에이전트를 페이즈별로 동시에 띄운 뒤, 검토 결과를 R1~R5 경로로 나눠
문제가 된 에이전트만 다시 돌린다. run_log.json은 여기서만 쓴다.

리포트 내용(섹션·지시문·문구·스키마)은 모두 config/ 파일에서 온다.
"""

import asyncio
import csv
import io
import json
import re
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .charts import render, validate
from .llm import LLM
from .specs import Specs
from .workspace import RunLog, Workspace, now_kst

MARKER = re.compile(r"<!--\s*section:([a-z0-9\-]+)\s*-->")


@dataclass
class Issue:
    route: str
    target: str
    location: str
    problem: str
    fix_hint: str
    severity: str
    reviewer: str

    def line(self) -> str:
        return f"[{self.reviewer}] {self.location}: {self.problem} → {self.fix_hint}"


def normalize_issue(raw: dict, reviewer: str, specs: Specs) -> Issue:
    """경로는 target으로 정한다. 검토자가 route를 잘못 붙여도 받는 쪽이 맞게 간다."""
    target = raw.get("target", specs.writer["name"])
    if target == specs.charter["name"]:
        route = "R2"
    elif specs.is_analyst(target):
        route = "R3"
    else:
        route, target = "R1", specs.writer["name"]
    return Issue(
        route=route,
        target=target,
        location=raw.get("location", ""),
        problem=raw.get("problem", ""),
        fix_hint=raw.get("fix_hint", ""),
        severity=raw.get("severity", "blocker"),
        reviewer=reviewer,
    )


def _csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["metric", "period", "value", "unit", "source_id"])
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in w.fieldnames})
    return buf.getvalue()


def _chart_id(raw: str, i: int) -> str:
    cid = re.sub(r"[^a-z0-9\-]+", "-", raw.lower()).strip("-")
    return cid or f"chart-{i + 1}"


class Orchestrator:
    def __init__(
        self,
        llm: LLM,
        ws: Workspace,
        specs: Specs,
        *,
        brief_path: Path,
        reference_pdf: Path,
        max_rework: int,
        use_search: bool,
        say: Callable[[str], None] = print,
        emit: Callable[[dict], None] = lambda e: None,
    ):
        self.llm = llm
        self.ws = ws
        self.sp = specs
        self.d = specs.dirs
        self.writer = specs.writer["name"]
        self.charter = specs.charter["name"]
        self.brief_path = Path(brief_path)
        self.reference_pdf = Path(reference_pdf)
        self.max_rework = max_rework
        self.use_search = use_search
        self._say = say
        self._emit = emit
        self._t0 = time.monotonic()
        self.runlog = RunLog(ws, {"model": llm.model, "reference": self.reference_pdf.name})
        self.last_entry: dict[str, int] = {}
        self.rework: dict[tuple[str, str], int] = defaultdict(int)
        self.unresolved: list[str] = []
        self.charts: list[dict] = []

    # ------------------------------------------------------------ 공통

    def say(self, msg: str) -> None:
        line = f"[{time.monotonic() - self._t0:6.1f}s] {msg}"
        self._say(line)
        self._emit({"type": "log", "msg": line})

    def start(self, agent: str, phase: str, route: str | None = None) -> str:
        self._emit({"type": "start", "agent": agent, "phase": phase, "route": route})
        return now_kst()

    def record(self, agent, phase, started, *, status="완료", route=None, outputs=(), summary="") -> int:
        entry_id = self.runlog.add(
            phase=phase,
            agent=agent,
            route=route,
            rerun_of=self.last_entry.get(agent),
            started_at=started,
            finished_at=now_kst(),
            status=status,
            outputs=list(outputs),
            log_summary=summary,
        )
        self.last_entry[agent] = entry_id
        self._emit({"type": "done" if status == "완료" else "fail", "agent": agent, "phase": phase,
                    "route": route, "summary": summary, "outputs": list(outputs)})
        return entry_id

    def can_rework(self, agent: str, route: str) -> bool:
        if self.rework[(agent, route)] >= self.max_rework:
            return False
        self.rework[(agent, route)] += 1
        return True

    def brief(self) -> str:
        return self.ws.read(f"{self.d['brief']}/brief.md")

    def _rework_parts(self, route: str, feedback) -> list[str]:
        items = "\n".join(f"- {f}" for f in feedback)
        return [self.sp.msg("rework_reason", route=route, items=items), self.sp.msg("rework_tail")]

    # ------------------------------------------------------------ 실행

    async def run(self) -> Path:
        self.p0_brief()
        await self.p1_analysis()
        await self.p2_writing()
        await self.p3_review()
        return self.p4_finalize()

    # P0 · 메인 세션 ------------------------------------------------

    def p0_brief(self) -> None:
        started = self.start(self.sp.main, "P0")
        rel = f"{self.d['brief']}/brief.md"
        self.ws.write(rel, self.brief_path.read_text(encoding="utf-8"))
        self.record(self.sp.main, "P0", started, outputs=[rel], summary="작업 지시서 배치")
        self.say("P0 범위: brief.md 배치")

    # P1 · 분석 ----------------------------------------------------

    async def p1_analysis(self) -> None:
        names = self.sp.analyst_names
        self.say(f"P1 분석 시작: {len(names)}개 동시 실행")
        outs = await asyncio.gather(*(self.run_analyst(n) for n in names))
        self.handle_escalations(dict(zip(names, outs)))

    async def run_analyst(self, name: str, *, route: str | None = None, feedback=()) -> dict:
        spec = self.sp.analysts[name]
        d = f"{self.d['analysis']}/{name}"
        started = self.start(name, "P1", route)
        try:
            parts = [
                self.sp.msg("brief", brief=self.brief()),
                self.sp.msg("analyst_task", section=spec.section, pages=spec.pages, task=spec.task),
            ]
            if self.use_search and not feedback:
                notes = await self.llm.research(
                    agent=name,
                    system=self.sp.prompt("research"),
                    prompt=self.sp.msg("research_request", section=spec.section, task=spec.task),
                )
                self.ws.write(f"{d}/research.md", notes)
            if notes := self.ws.read(f"{d}/research.md"):
                parts.append(self.sp.msg("research_notes", notes=notes))
            if feedback:
                parts += [
                    self.sp.msg("prev_section", text=self.ws.read(f"{d}/section.md")),
                    self.sp.msg("prev_data", text=self.ws.read(f"{d}/data.csv")),
                    *self._rework_parts(route, feedback),
                ]
            out = await self.llm.generate_json(
                agent=name,
                system=self.sp.prompt("analyst"),
                prompt="\n\n".join(parts),
                schema=self.sp.schema("analyst"),
                attachments=[self.reference_pdf],
            )
        except Exception as e:  # 분석 하나가 실패해도 나머지는 계속 간다
            self.ws.write(f"{d}/error.md", f"{type(e).__name__}: {e}\n")
            self.unresolved.append(f"{name}: {self.sp.txt('analysis_failed')} ({e})")
            self.record(name, "P1", started, status="실패", route=route, outputs=[f"{d}/error.md"], summary=str(e))
            self.say(f"  ✗ {name} 실패: {e}")
            return {"escalations": []}

        t = self.sp.txt
        self.ws.write(f"{d}/section.md", f"## {spec.section}\n\n{out['section_md'].strip()}\n")
        self.ws.write(f"{d}/data.csv", _csv(out["data"]))
        self.ws.write(f"{d}/sources.md", t("sources_header") + "".join(t("sources_row", **s) for s in out["sources"]))
        self.ws.write(
            f"{d}/handoff.md",
            t("handoff_conclusions")
            + "".join(f"- {c}\n" for c in out["conclusions"])
            + t("handoff_candidates")
            + "".join(f"- {c['name']}: {c['reason']}\n" for c in out["shortage_candidates"]),
        )
        self.ws.write(f"{d}/result.json", json.dumps(out, ensure_ascii=False, indent=2))
        files = [f"{d}/{f}" for f in ("section.md", "data.csv", "sources.md", "handoff.md")]
        self.record(name, "P1", started, route=route, outputs=files, summary=out.get("log_summary", ""))
        self.say(f"  ✓ {name}{f' ({route})' if route else ''}: 숫자 {len(out['data'])}개")
        return out

    def handle_escalations(self, results: dict[str, dict]) -> None:
        """R5: 분석 에이전트가 올린 범위·데이터 문제를 메인 세션이 확정해 brief에 적는다."""
        items = [(n, e) for n, out in results.items() for e in out.get("escalations", [])]
        if not items:
            return
        started = self.start(self.sp.main, "P1", "R5")
        header = self.sp.txt("r5_header")
        brief = self.brief().rstrip()
        lines = [] if header in brief else ["", header, ""]
        for name, e in items:
            if e["kind"] == "out_of_scope":
                decision = self.sp.txt("r5_out_of_scope")
            else:
                decision = self.sp.txt("r5_no_data")
                self.unresolved.append(f"{name}: {e['detail']}")
            lines.append(f"- ({name}) {e['detail']} → {decision}")
        rel = f"{self.d['brief']}/brief.md"
        self.ws.write(rel, brief + "\n" + "\n".join(lines) + "\n")
        self.record(self.sp.main, "P1", started, route="R5", outputs=[rel], summary=f"{len(items)}건 확정")
        self.say(f"  ↩ R5 {len(items)}건 → brief.md에 확정 사항 추가")

    def analysis_bundle(self, *, sections: bool) -> str:
        out = []
        for n in self.sp.analyst_names:
            d = f"{self.d['analysis']}/{n}"
            block = [f"### [{n}]"]
            if sections:
                block += [self.ws.read(f"{d}/section.md"), "#### handoff", self.ws.read(f"{d}/handoff.md")]
            block += ["#### data.csv", self.ws.read(f"{d}/data.csv"), "#### sources.md", self.ws.read(f"{d}/sources.md")]
            out.append("\n".join(block))
        return "\n\n".join(out)

    # P2 · 작성 ----------------------------------------------------

    async def p2_writing(self) -> None:
        self.say(f"P2 작성 시작: {self.writer} · {self.charter} 동시 실행")
        w, _ = await asyncio.gather(self.run_writer(), self.run_charter())

        for attempt in range(self.max_rework + 1):  # R4
            questions = w["questions"]
            if not questions:
                return
            if attempt == self.max_rework:
                self.unresolved += [f"{q['to_agent']}: {q['question']}" for q in questions]
                return
            by_agent: dict[str, list[str]] = defaultdict(list)
            for q in questions:
                by_agent[q["to_agent"]].append(q["question"])
            targets = [a for a in by_agent if self.sp.is_analyst(a) and self.can_rework(a, "R4")]
            self.unresolved += [f"{a}: {q}" for a in by_agent if a not in targets for q in by_agent[a]]
            if not targets:
                return
            self.say(f"  ↩ R4 writer 질문 → {', '.join(targets)} 보강")
            outs = await asyncio.gather(*(self.run_analyst(a, route="R4", feedback=by_agent[a]) for a in targets))
            self.handle_escalations(dict(zip(targets, outs)))
            note = [self.sp.msg("r4_note")]
            w, _ = await asyncio.gather(
                self.run_writer(route="R4", feedback=note), self.run_charter(route="R4", feedback=note)
            )

    async def run_writer(self, *, route: str | None = None, feedback=()) -> dict:
        started = self.start(self.writer, "P2", route)
        draft = f"{self.d['draft']}/report.md"
        order = "\n".join(
            self.sp.msg("writer_order_item", section=s.section, pages=s.pages, name=n)
            for n, s in self.sp.analysts.items()
        )
        parts = [
            self.sp.msg("brief", brief=self.brief()),
            self.sp.msg("writer_order", items=order),
            self.sp.msg("analysis_bundle", dir=self.d["analysis"], bundle=self.analysis_bundle(sections=True)),
        ]
        if feedback:
            parts += [self.sp.msg("prev_draft", text=self.ws.read(draft)), *self._rework_parts(route, feedback)]
        out = await self.llm.generate_json(
            agent=self.writer,
            system=self.sp.prompt(self.sp.writer["prompt"]),
            prompt="\n\n".join(parts),
            schema=self.sp.schema(self.sp.writer["schema"]),
        )
        t = self.sp.txt
        qpath = f"{self.d['draft']}/questions.md"
        self.ws.write(draft, out["report_md"])
        self.ws.write(
            qpath,
            t("questions_header")
            + ("".join(f"- {q['to_agent']}: {q['question']}\n" for q in out["questions"]) or t("questions_empty")),
        )
        missing = [n for n in self.sp.analyst_names if f"section:{n}" not in out["report_md"]]
        summary = out.get("log_summary", "") + (f" / 차트 자리 누락: {missing}" if missing else "")
        self.record(self.writer, "P2", started, route=route, outputs=[draft, qpath], summary=summary)
        self.say(f"  ✓ {self.writer}{f' ({route})' if route else ''}: 질문 {len(out['questions'])}개")
        return out

    async def run_charter(self, *, route: str | None = None, feedback=()) -> dict:
        started = self.start(self.charter, "P2", route)
        cdir = f"{self.d['draft']}/charts"
        parts = [self.sp.msg("analysis_data", dir=self.d["analysis"], bundle=self.analysis_bundle(sections=False))]
        if feedback:
            parts += [self.sp.msg("prev_charts", text=self.ws.read(f"{cdir}/specs.json")), *self._rework_parts(route, feedback)]
        out = await self.llm.generate_json(
            agent=self.charter,
            system=self.sp.prompt(self.sp.charter["prompt"]),
            prompt="\n\n".join(parts),
            schema=self.sp.schema(self.sp.charter["schema"]),
        )
        valid, skipped = [], []
        for i, spec in enumerate(out["charts"]):
            spec["id"] = _chart_id(spec.get("id", ""), i)
            if err := validate(spec):
                skipped.append(f"{spec['id']}: {err}")
                continue
            rel = f"{cdir}/{spec['id']}.png"
            self.ws.archive(rel)
            render(spec, self.ws.path(rel), self.sp.chart_style)
            valid.append(spec)
        self.charts = valid
        t = self.sp.txt
        self.ws.write(f"{cdir}/specs.json", json.dumps(valid, ensure_ascii=False, indent=2))
        self.ws.write(
            f"{cdir}/index.md",
            t("charts_header")
            + "".join(f"- `{c['id']}.png` ({c['section']}) {c['title']} — {c['source']}\n" for c in valid)
            + (t("charts_skipped") + "".join(f"- {s}\n" for s in skipped) if skipped else ""),
        )
        self.record(
            self.charter, "P2", started, route=route,
            outputs=[f"{cdir}/specs.json", f"{cdir}/index.md"],
            summary=out.get("log_summary", "") + (f" / 제외 {len(skipped)}개" if skipped else ""),
        )
        self.say(f"  ✓ {self.charter}{f' ({route})' if route else ''}: 차트 {len(valid)}개"
                 + (f", 제외 {len(skipped)}개" if skipped else ""))
        return out

    # P3 · 검토 ----------------------------------------------------

    async def p3_review(self) -> None:
        reviewers = self.sp.reviewers
        for rnd in range(1, self.max_rework + 2):
            self.say(f"P3 검토 {rnd}회차: {' · '.join(r['name'] for r in reviewers)} 동시 실행")
            results = await asyncio.gather(*(self.run_reviewer(r, rnd) for r in reviewers))
            issues = [
                normalize_issue(i, r["name"], self.sp) for r, out in zip(reviewers, results) for i in out["issues"]
            ]
            blockers = [i for i in issues if i.severity == "blocker"]
            if not blockers:
                self.say("  ✓ 검토 통과")
                return
            if rnd > self.max_rework:
                self.unresolved += [f"{i.target}: {i.line()}" for i in blockers]
                self.say(f"  ! 재작업 한도 도달, 남은 지적 {len(blockers)}건은 [확인필요]로 발간")
                return
            await self.route_issues(blockers)

    async def run_reviewer(self, rv: dict, rnd: int) -> dict:
        name = rv["name"]
        started = self.start(name, "P3")
        draft = f"{self.d['draft']}/report.md"
        specs_json = f"{self.d['draft']}/charts/specs.json"
        parts = [
            self.sp.msg("brief", brief=self.brief()),
            self.sp.msg("draft", path=draft, text=self.ws.read(draft)),
            self.sp.msg("chart_specs", path=specs_json, text=self.ws.read(specs_json)),
        ]
        if rv["needs_data"]:
            parts.append(self.sp.msg("analysis_data", dir=self.d["analysis"], bundle=self.analysis_bundle(sections=False)))
        out = await self.llm.generate_json(
            agent=name, system=self.sp.prompt(rv["prompt"]), prompt="\n\n".join(parts), schema=self.sp.schema(rv["schema"])
        )
        rows = "".join(
            f"| {i['severity']} | {i['route']} | {i['target']} | {i['location']} | {i['problem']} | {i['fix_hint']} |\n"
            for i in out["issues"]
        )
        base = f"{self.d['review']}/{rv['output']}"
        self.ws.write(f"{base}.md", self.sp.txt("review_header", name=name, round=rnd, verdict=out["verdict"]) + rows)
        self.ws.write(f"{base}.json", json.dumps(out, ensure_ascii=False, indent=2))
        n_block = sum(i["severity"] == "blocker" for i in out["issues"])
        self.record(name, "P3", started, outputs=[f"{base}.md"],
                    summary=f"{out['verdict']} · blocker {n_block}개 · {out.get('log_summary', '')}")
        self.say(f"  ✓ {name}: {out['verdict']} (blocker {n_block}개)")
        return out

    async def route_issues(self, blockers: list[Issue]) -> None:
        """R1·R2·R3로 나눠 해당 에이전트만 다시 돌린다. 분석(R3)을 먼저, 그다음 작성 2개를 동시에."""
        by: dict[str, list[Issue]] = defaultdict(list)
        for i in blockers:
            by[i.target].append(i)

        r3 = [a for a in self.sp.analyst_names if a in by]
        r3_run = [a for a in r3 if self.can_rework(a, "R3")]
        for a in set(r3) - set(r3_run):
            self.unresolved += [f"{a}: {i.line()}" for i in by[a]]
        if r3_run:
            self.say(f"  ↩ R3 → {', '.join(r3_run)}")
            outs = await asyncio.gather(
                *(self.run_analyst(a, route="R3", feedback=[i.line() for i in by[a]]) for a in r3_run)
            )
            self.handle_escalations(dict(zip(r3_run, outs)))

        tasks = []
        changed = [self.sp.msg("r3_note")] if r3_run else []
        for agent, route, runner in ((self.writer, "R1", self.run_writer), (self.charter, "R2", self.run_charter)):
            own = by.get(agent, [])
            if own and not self.can_rework(agent, route):
                self.unresolved += [f"{agent}: {i.line()}" for i in own]
                own = []
            if own or r3_run:
                self.say(f"  ↩ {route if own else 'R3 후속'} → {agent}")
                tasks.append(runner(route=route if own else "R3", feedback=[i.line() for i in own] + changed))
        results = await asyncio.gather(*tasks)
        for out in results:  # 검토 단계에서 새로 나온 writer 질문은 더 돌리지 않는다
            self.unresolved += [f"{q['to_agent']}: {q['question']}" for q in out.get("questions", [])]

    # P4 · 메인 세션 -----------------------------------------------

    def p4_finalize(self) -> Path:
        started = self.start(self.sp.main, "P4")
        report = self.ws.read(f"{self.d['draft']}/report.md")
        by_section: dict[str, list[dict]] = defaultdict(list)
        for c in self.charts:
            by_section[c["section"]].append(c)

        def block(cs: list[dict]) -> str:
            return "\n".join(f"![{c['title']}](charts/{c['id']}.png)\n\n<sub>{c['source']}</sub>\n" for c in cs)

        used: set[str] = set()

        def put(m: re.Match) -> str:
            used.add(m.group(1))
            return block(by_section.get(m.group(1), []))

        final = MARKER.sub(put, report).rstrip() + "\n"
        rest = [c for s, cs in by_section.items() if s not in used for c in cs]
        if rest:
            final += self.sp.txt("final_charts_appendix") + block(rest)
        if self.unresolved:
            final += self.sp.txt("final_unresolved") + "".join(f"- {u}\n" for u in dict.fromkeys(self.unresolved))

        out_dir = self.ws.path(f"{self.d['final']}/charts")
        out_dir.mkdir(parents=True, exist_ok=True)
        for c in self.charts:
            shutil.copy2(self.ws.path(f"{self.d['draft']}/charts/{c['id']}.png"), out_dir / f"{c['id']}.png")
        rel = f"{self.d['final']}/report.md"
        path = self.ws.write(rel, final)
        self.record(self.sp.main, "P4", started, outputs=[rel],
                    summary=f"차트 {len(self.charts)}개 · [확인필요] {len(set(self.unresolved))}건")
        self.say(f"P4 발간: {path}")
        return path
