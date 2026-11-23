"""chart-maker가 낸 차트 스펙을 matplotlib으로 PNG로 그린다. 스타일은 config/chart_style.json."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402


def _installed(fonts: list[str]) -> list[str]:
    """설정 글꼴 중 이 PC에 있는 것만 쓴다 (없는 글꼴 경고 방지)."""
    have = {f.name for f in font_manager.fontManager.ttflist}
    return [f for f in fonts if f in have] or ["DejaVu Sans"]


def validate(spec: dict) -> str | None:
    """문제가 있으면 이유를, 없으면 None을 돌려준다."""
    n = len(spec.get("x", []))
    if n == 0:
        return "x가 비어 있음"
    if not spec.get("series"):
        return "series가 비어 있음"
    for s in spec["series"]:
        if len(s.get("values", [])) != n:
            return f"series '{s.get('name')}' 길이({len(s.get('values', []))})가 x 길이({n})와 다름"
    return None


def render(spec: dict, out: Path, style: dict) -> None:
    plt.rcParams["font.family"] = _installed(style["fonts"])
    plt.rcParams["axes.unicode_minus"] = False
    palette = style["palette"]
    fig, ax = plt.subplots(figsize=tuple(style["figsize"]), dpi=style["dpi"])
    x, series = spec["x"], spec["series"]
    if spec["kind"] == "bar":
        width = 0.8 / len(series)
        for i, s in enumerate(series):
            pos = [j + (i - (len(series) - 1) / 2) * width for j in range(len(x))]
            ax.bar(pos, s["values"], width=width, label=s["name"], color=palette[i % len(palette)])
        ax.set_xticks(range(len(x)), x)
    else:
        for i, s in enumerate(series):
            ax.plot(x, s["values"], label=s["name"], color=palette[i % len(palette)], linewidth=2)
    ax.set_title(spec["title"], loc="left", fontsize=style["title_size"], fontweight="bold")
    ax.set_ylabel(spec.get("unit", ""))
    ax.axhline(0, color="#999", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    if len(series) > 1:
        ax.legend(frameon=False, fontsize=8)
    fig.text(0.01, 0.01, spec.get("source", ""), fontsize=style["source_size"], color="#666")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
