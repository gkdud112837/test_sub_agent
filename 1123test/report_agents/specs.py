"""config/ 아래 파일에서 에이전트 정의·지시문·스키마·문구를 읽는다.

코드에는 리포트 내용이 없다. 섹션·지시문·문구를 바꾸려면 config/ 파일을 고친다.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalystSpec:
    name: str
    label: str
    section: str
    pages: str
    task: str


class Specs:
    def __init__(self, config_dir: Path):
        self.dir = Path(config_dir)
        self.raw = self._json("agents.json")
        cfg = self.raw
        self.reference_source: str = cfg["reference_source"]
        self.dirs: dict[str, str] = cfg["workspace_dirs"]
        self.main: str = cfg["main"]["name"]
        self.analysts = {a["name"]: AnalystSpec(**a) for a in cfg["analysts"]}
        self.analyst_names: tuple[str, ...] = tuple(self.analysts)
        self.writer: dict = cfg["writer"]
        self.charter: dict = cfg["charter"]
        self.reviewers: list[dict] = cfg["reviewers"]
        self.messages: dict[str, str] = self._json("prompts/messages.json")
        self.text: dict[str, str] = self._json("output_text.json")
        self.chart_style: dict = self._json("chart_style.json")
        self._enums = {
            "$ANALYSTS": list(self.analyst_names),
            "$REVIEW_TARGETS": [self.writer["name"], self.charter["name"], *self.analyst_names],
        }

    def _json(self, rel: str):
        return json.loads((self.dir / rel).read_text(encoding="utf-8"))

    def prompt(self, name: str) -> str:
        """시스템 지시문. {{common}}, {{reference_source}} 자리를 채운다."""
        common = (self.dir / "prompts" / "common.md").read_text(encoding="utf-8")
        text = (self.dir / "prompts" / f"{name}.md").read_text(encoding="utf-8")
        text = text.replace("{{common}}", common)
        return text.replace("{{reference_source}}", self.reference_source).strip()

    def schema(self, name: str) -> dict:
        """응답 스키마. enum 자리 표시($ANALYSTS 등)를 agents.json 이름으로 채운다."""

        def fill(node):
            if isinstance(node, dict):
                return {
                    k: (self._enums[v] if k == "enum" and isinstance(v, str) else fill(v))
                    for k, v in node.items()
                }
            if isinstance(node, list):
                return [fill(v) for v in node]
            return node

        return fill(self._json(f"schemas/{name}.json"))

    def msg(self, key: str, **kw) -> str:
        return self.messages[key].format(**kw)

    def txt(self, key: str, **kw) -> str:
        return self.text[key].format(**kw) if kw else self.text[key]

    def is_analyst(self, name: str) -> bool:
        return name in self.analysts
