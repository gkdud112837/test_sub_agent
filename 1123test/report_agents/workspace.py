"""공유 작업 공간과 실행 로그.

- 에이전트 결과는 모두 workspace/ 아래 파일로 남는다.
- 같은 파일을 다시 쓰면 이전 판은 이름_v1, _v2 ...로 보관한다.
- run_log.json은 오케스트레이터(메인 세션)만 쓴다. 추가만 하고 고치지 않는다.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, rel: str) -> Path:
        return self.root / rel

    def archive(self, rel: str) -> Path | None:
        """기존 파일을 _vN으로 옮기고 새 경로를 돌려준다."""
        p = self.path(rel)
        if not p.exists():
            return None
        n = 1
        while (target := p.with_name(f"{p.stem}_v{n}{p.suffix}")).exists():
            n += 1
        p.rename(target)
        return target

    def write(self, rel: str, text: str) -> Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.archive(rel)
        p.write_text(text, encoding="utf-8")
        return p

    def read(self, rel: str, default: str = "") -> str:
        p = self.path(rel)
        return p.read_text(encoding="utf-8") if p.exists() else default


class RunLog:
    def __init__(self, ws: Workspace, meta: dict):
        self.file = ws.path("run_log.json")
        if self.file.exists():
            self.data = json.loads(self.file.read_text(encoding="utf-8"))
        else:
            self.data = {**meta, "entries": []}
        self.data.setdefault("runs", []).append({"started_at": now_kst(), **meta})
        self._save()

    def add(self, **entry) -> int:
        entries = self.data["entries"]
        entry_id = (entries[-1]["id"] + 1) if entries else 1
        entries.append({"id": entry_id, **entry})
        self._save()
        return entry_id

    def _save(self) -> None:
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.file)
