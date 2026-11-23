"""dry-run용 가짜 LLM. 응답은 코드가 아니라 fixtures/dry_run.json에서 읽는다.

API 키 없이 병렬 실행·R1~R5 경로·파일 기록이 제대로 도는지 확인하는 데 쓴다.
"""

import asyncio
import copy
import json
from collections import Counter
from pathlib import Path

from .specs import Specs


def _fill(node, values: dict):
    if isinstance(node, str):
        for k, v in values.items():
            node = node.replace("{" + k + "}", v)
        return node
    if isinstance(node, list):
        return [_fill(v, values) for v in node]
    if isinstance(node, dict):
        return {k: _fill(v, values) for k, v in node.items()}
    return node


class FakeLLM:
    model = "dry-run"

    def __init__(self, fixture: Path, specs: Specs, delay: float | None = None):
        self.fx = json.loads(Path(fixture).read_text(encoding="utf-8"))
        self.specs = specs
        self.delay = self.fx["delay_sec"] if delay is None else delay
        self.calls: Counter[str] = Counter()
        self.active = 0
        self.peak = 0

    async def _tick(self) -> None:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.active -= 1

    def _values(self, agent: str) -> dict:
        spec = self.specs.analysts.get(agent)
        return {"agent": agent, "section": spec.section if spec else agent}

    async def research(self, *, agent, system, prompt, attachments=()):
        await self._tick()
        return _fill(self.fx["research"], self._values(agent))

    async def generate_json(self, *, agent, system, prompt, schema, attachments=()):
        self.calls[agent] += 1
        n = self.calls[agent]
        await self._tick()
        if self.specs.is_analyst(agent):
            out = copy.deepcopy(self.fx["analyst"])
            out.update(self.fx.get("analyst_overrides", {}).get(agent, {}).get(str(n), {}))
            return _fill(out, self._values(agent))
        seq = self.fx["responses"][agent]
        return copy.deepcopy(seq[min(n, len(seq)) - 1])
