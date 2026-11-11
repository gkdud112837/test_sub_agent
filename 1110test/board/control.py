"""VOC 분류 관제 프로그램.

관제 액션(게이트 점검 · 채점 · 로그 집계)을 실행해 board/status.json · board/status.js 를 만들고,
실행 결과를 훅 로그(.claude/logs/events.jsonl)에 ControlCheck 이벤트로 남긴다.
board/index.html 이 status.js 를 읽어 화면에 그린다.

사용:
  python -I -X utf8 board/control.py            # 1회 점검
  python -I -X utf8 board/control.py --open     # 1회 점검 후 관제 화면 열기
  python -I -X utf8 board/control.py --watch 5  # 5초마다 반복 점검 (Ctrl+C로 종료)
  python -I -X utf8 board/control.py --no-log   # events.jsonl 기록 생략

표준 라이브러리만 사용한다 (설치 필요 없음).
"""
import argparse, collections, csv, glob, json, math, os, re, subprocess, sys, time, webbrowser

BOARD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("VOC_PROJECT_ROOT") or os.path.dirname(BOARD)
PARTS_DIR = os.path.join(ROOT, "ax", "demo", "parts")
SCORECARD = os.path.join(ROOT, "ax", "demo", "scorecard.md")
GOLDEN = os.path.join(ROOT, "ax", "demo", "golden.csv")
EVENTS = os.path.join(ROOT, ".claude", "logs", "events.jsonl")
LOGGER = os.path.join(ROOT, ".claude", "hooks", "log_event.py")

HEADER = ["voc_id", "tag", "evidence", "note"]
REVIEW_MAX = 0.05
SCORE_MIN = 89
GOLDEN_MIN = 9
EVIDENCE_MAX = 15


def first(pattern):
    hits = glob.glob(os.path.join(ROOT, pattern))
    return hits[0] if hits else None


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


# ── 기준 데이터 ─────────────────────────────────────────────
def allowed_tags():
    """painpoint_def.md 의 '허용 태그:' 줄에서 직접 읽는다."""
    p = first("painpoint-*/painpoint/painpoint_def.md")
    if p:
        for line in open(p, encoding="utf-8"):
            if "허용 태그" in line:
                tags = [t.strip() for t in line.split(":", 1)[1].split("·")]
                return [t for t in tags if t], p
    return ["P1", "P2", "P3", "H1", "H2", "해당없음", "검토"], None


def archive():
    meta_p = first("archive-*/archive/metadata.csv")
    meta = list(csv.DictReader(open(meta_p, encoding="utf-8-sig"))) if meta_p else []
    texts = {}
    for p in glob.glob(os.path.join(ROOT, "archive-*", "archive", "batch*", "r_*.md")):
        batch = int(re.search(r"batch(\d+)", p).group(1))
        body = open(p, encoding="utf-8").read().split("---", 2)[2].strip()
        texts[os.path.basename(p)[:-3]] = (batch, body)
    return meta, texts


# ── 관제 액션 1: 게이트 점검 ─────────────────────────────────
def check_part(path, allowed, texts):
    n_part = int(re.search(r"part_(\d+)", path).group(1))
    rows = read_csv(path)
    header, body = (rows[0], rows[1:]) if rows else ([], [])
    expected = sorted(v for v, (b, _) in texts.items() if b == n_part)
    ids = [r[0] for r in body if r]
    issues = []

    # ① 범위
    if header != HEADER:
        issues.append(("범위", "-", f"헤더 오류: {header}"))
    for v, c in collections.Counter(ids).items():
        if c > 1:
            issues.append(("범위", v, f"중복 {c}회"))
    for v in sorted(set(expected) - set(ids)):
        issues.append(("범위", v, "누락"))
    for v in sorted(set(ids) - set(expected)):
        issues.append(("범위", v, "다른 묶음 · 없는 ID"))
    range_bad = sum(1 for i in issues if i[0] == "범위")

    # ② 근거 · ③ 상식
    ev_bad = sense_bad = 0
    tags = collections.Counter()
    review = []
    for r in body:
        r = (r + ["", "", "", ""])[:4]
        v, tag, ev, note = r
        tags[tag] += 1
        txt = texts.get(v, (0, ""))[1]
        if not ev:
            ev_bad += 1; issues.append(("근거", v, "evidence 없음"))
        elif len(ev) > EVIDENCE_MAX:
            ev_bad += 1; issues.append(("근거", v, f"{len(ev)}자 (15자 초과)"))
        elif ev not in txt:
            ev_bad += 1; issues.append(("근거", v, f"원문에 없음: {ev}"))
        if tag not in allowed:
            sense_bad += 1; issues.append(("상식", v, f"허용 밖 태그: {tag}"))
        elif tag == "검토" and not note.strip():
            sense_bad += 1; issues.append(("상식", v, "검토 이유 누락"))
        elif tag != "검토" and note.strip():
            sense_bad += 1; issues.append(("상식", v, "검토가 아닌데 note 있음"))
        if tag == "검토":
            review.append({"voc_id": v, "note": note})

    n = max(len(body), 1)
    # 내림 처리: 불량이 1건이라도 있으면 100점이 되지 않게 한다
    score = lambda bad, total: max(0, math.floor(100 * (1 - bad / max(total, 1))))
    return {
        "part": os.path.basename(path)[:-4], "batch": n_part, "rows": len(body), "expected": len(expected),
        "scores": {"range": score(range_bad + (10 if header != HEADER else 0), max(len(expected), 1)),
                   "evidence": score(ev_bad, n), "sense": score(sense_bad, n)},
        "tags": dict(tags), "review": review, "issues": issues,
        "mtime": int(os.path.getmtime(path)),
    }


# ── 관제 액션 2: 채점관 점수 · 승인 상태 읽기 ─────────────────
def read_scorecard():
    if not os.path.exists(SCORECARD):
        return {"exists": False}
    text = open(SCORECARD, encoding="utf-8").read()
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0] and not cells[0].startswith("-"):
            rows[cells[0]] = {"value": cells[1], "rule": cells[2], "result": cells[3]}
    title = text.splitlines()[0].lstrip("# ").strip() if text else ""
    pick = lambda key: next((v for k, v in rows.items() if key in k), None)
    num = lambda r: int(re.match(r"\d+", r["value"]).group()) if r and re.match(r"\d+", r["value"]) else None
    appr = pick("승인")
    return {
        "exists": True, "title": title, "mtime": int(os.path.getmtime(SCORECARD)),
        "scores": {"range": num(pick("범위")), "evidence": num(pick("근거")), "sense": num(pick("상식"))},
        "approval": appr,
        "approved": bool(appr and ("완료" in appr["result"] or "승인" in appr["result"] and "대기" not in appr["result"])),
    }


# ── 관제 액션 3: 골든셋 비교 ──────────────────────────────────
def check_golden(all_rows):
    if not os.path.exists(GOLDEN):
        return {"exists": False}
    mine = {r[0]: r[1] for r in all_rows}
    g = [r for r in read_csv(GOLDEN)[1:] if r]
    detail = [{"voc_id": r[0], "golden": r[1], "mine": mine.get(r[0], "—"), "ok": mine.get(r[0]) == r[1]} for r in g]
    return {"exists": True, "agree": sum(d["ok"] for d in detail), "total": len(detail), "detail": detail}


# ── 관제 액션 4: 훅 로그 집계 ────────────────────────────────
def load_events():
    ev = []
    if os.path.exists(EVENTS):
        for line in open(EVENTS, encoding="utf-8"):
            try:
                ev.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return ev


# ── 관제 액션 5: 단계별 진행 중 감지 ──────────────────────────
ACTIVE_WINDOW = 15          # 최근 N초 안의 작업이면 '진행 중'
MARK_TIMEOUT = 600          # StageMark start 후 end 없이 10분이 지나면 해제

# 단계 → (파일 경로 패턴, 판단 근거 설명)
STAGE_RULES = {
    1: (r"archive[^\"]*[\\/](batch\d+[\\/]r_\d+\.md|metadata\.csv)", "원문 · ID 목록 읽는 중"),
    2: (r"ax[\\/]demo[\\/]parts[\\/]part_\d+\.csv", "part 파일에 근거 구절 기록 중"),
    3: (r"painpoint_def\.md", "허용 태그 · 판정 기준 확인 중"),
    4: (r"check_gates\.py", "검토 비율 점검 중"),
    5: (r"scorecard\.md|review-grader", "채점관 채점 중"),
    6: (r"golden\.csv", "골든셋 비교 중"),
    7: (r"승인", "승인 처리 중"),
}


def event_text(e):
    """이벤트에서 경로 · 명령 · 프롬프트 등 판단에 쓸 글자를 모은다."""
    ti = e.get("tool_input") or {}
    parts = [str(ti.get(k, "")) for k in ("file_path", "path", "pattern", "command", "description", "prompt")]
    if e.get("hook_event_name") == "UserPromptSubmit":
        parts.append(str(e.get("prompt", "")))
    return " ".join(parts)


def active_stages(ev, now):
    active = {}
    # (1) 직접 표시: StageMark {stage, state: start|end}
    marks = {}
    for e in ev:
        if e.get("hook_event_name") == "StageMark":
            marks[int(e.get("stage", 0))] = e
    for st, e in marks.items():
        if e.get("state") == "start" and now - e.get("ts", 0) < MARK_TIMEOUT:
            active[st] = {"since": e.get("ts"), "why": e.get("note") or "시작 표시됨", "how": "mark"}
    # (2) 자동 감지: 최근 ACTIVE_WINDOW 초의 도구 · 프롬프트 이벤트
    for e in ev:
        ts = e.get("ts", 0)
        if now - ts > ACTIVE_WINDOW or e.get("hook_event_name") in ("ControlCheck", "StageMark", "Stop"):
            continue
        txt = event_text(e)
        if "board" in txt and "control.py" in txt:  # 관제 자신의 실행은 제외
            continue
        for st, (pat, why) in STAGE_RULES.items():
            if st in marks and marks[st].get("state") == "end" and marks[st].get("ts", 0) >= ts:
                continue
            if re.search(pat, txt):
                who = "서브에이전트" if e.get("agent_id") else "메인"
                cur = active.get(st)
                if not cur or (cur["how"] == "auto" and ts > cur["since"]):
                    active[st] = {"since": ts, "why": f"{why} ({who} · {e.get('tool_name') or e.get('hook_event_name')})", "how": "auto"}
    return active


def read_events(ev, limit=40):
    if not os.path.exists(EVENTS):
        return {"exists": False}
    by_type = collections.Counter(e.get("hook_event_name", "?") for e in ev)
    by_tool = collections.Counter(e.get("tool_name") for e in ev if e.get("hook_event_name") == "PostToolUse")
    agents = collections.defaultdict(lambda: {"calls": 0, "last": 0, "type": ""})
    for e in ev:
        if e.get("agent_id") and e.get("hook_event_name") == "PostToolUse":
            a = agents[e["agent_id"]]; a["calls"] += 1; a["last"] = max(a["last"], e.get("ts", 0))
            a["type"] = e.get("agent_type", a["type"])

    def brief(e):
        ti = e.get("tool_input") or {}
        what = ti.get("description") or ti.get("file_path") or ti.get("pattern") or ti.get("prompt") \
            or e.get("prompt") or e.get("task") or ""
        return {"ts": e.get("ts"), "event": e.get("hook_event_name"), "tool": e.get("tool_name", ""),
                "what": str(what)[:120], "agent": bool(e.get("agent_id"))}

    return {
        "exists": True, "total": len(ev), "last_ts": ev[-1].get("ts") if ev else None,
        "by_type": dict(by_type.most_common()), "by_tool": dict(by_tool.most_common(8)),
        "agents": [{"id": k[:8], **v} for k, v in sorted(agents.items(), key=lambda x: -x[1]["last"])][:8],
        "special": [e for e in ev if e.get("hook_event_name") in ("GraderResult", "ControlCheck", "StageMark")][-8:],
        "recent": [brief(e) for e in ev[-limit:]][::-1],
    }


# ── 종합 ──────────────────────────────────────────────────
def run():
    allowed, def_path = allowed_tags()
    meta, texts = archive()
    part_paths = sorted(glob.glob(os.path.join(PARTS_DIR, "part_*.csv")))
    parts = [check_part(p, allowed, texts) for p in part_paths]
    all_rows = [r for p in part_paths for r in read_csv(p)[1:] if r]

    total = len(all_rows)
    tags = collections.Counter(r[1] for r in all_rows)
    review_n = tags.get("검토", 0)
    review_reason_missing = sum(1 for p in parts for i in p["issues"] if i[2] == "검토 이유 누락")
    batches = sorted({b for b, _ in texts.values()})
    covered = {p["batch"] for p in parts}

    def agg(key):
        w = sum(p["rows"] for p in parts) or 1
        return math.floor(sum(p["scores"][key] * p["rows"] for p in parts) / w) if parts else 0

    machine = {"range": agg("range"), "evidence": agg("evidence"), "sense": agg("sense")}
    if set(batches) - covered:  # 아직 없는 part 가 있으면 범위 점수에 반영
        machine["range"] = min(machine["range"], round(100 * len(covered) / max(len(batches), 1)))
    sc = read_scorecard()
    gold = check_golden(all_rows)
    raw_events = load_events()
    events = read_events(raw_events)
    now = int(time.time())
    active = active_stages(raw_events, now)

    def gate(no, name, ok, value, rule, who):
        state = "PASS" if ok is True else "FAIL" if ok is False else "WAIT"
        return {"no": no, "name": name, "state": state, "value": value, "rule": rule, "who": who,
                "active": active.get(no)}

    stale = sc.get("exists") and parts and max(p["mtime"] for p in parts) > sc["mtime"]
    gates = [
        gate(1, "ID 범위", machine["range"] >= SCORE_MIN and all(not [i for i in p["issues"] if i[0] == "범위"] for p in parts) and covered == set(batches),
             f"{total}/{len(texts)}행 · part {len(parts)}/{len(batches)}", "누락 0 · 중복 0", "① 범위 점수"),
        gate(2, "근거", machine["evidence"] >= SCORE_MIN and all(not [i for i in p["issues"] if i[0] == "근거"] for p in parts),
             f"불량 {sum(1 for p in parts for i in p['issues'] if i[0] == '근거')}행", "원문 그대로 · 15자 이내", "② 근거 판정"),
        gate(3, "태그", machine["sense"] >= SCORE_MIN and all(not [i for i in p["issues"] if i[0] == "상식"] for p in parts),
             f"허용 밖 {sum(1 for p in parts for i in p['issues'] if '허용 밖' in i[2])}행", f"허용 {len(allowed)}개", "③ 상식 점수"),
        gate(4, "검토 비율", (review_n / max(total, 1) <= REVIEW_MAX and review_reason_missing == 0) if total else None,
             f"{review_n}건 ({review_n / max(total, 1):.1%})", "≤ 5% · 이유 누락 0", "check"),
        gate(5, "채점 합격선", (all(v is not None and v >= SCORE_MIN for v in sc["scores"].values()) and not stale) if sc.get("exists") else None,
             " · ".join(f"{v if v is not None else '—'}" for v in sc.get("scores", {}).values()) + (" (채점 후 CSV 변경됨)" if stale else ""),
             "세 묶음 각 ≥ 89", "review-grader"),
        gate(6, "골든셋", (gold["agree"] >= GOLDEN_MIN) if gold.get("exists") else None,
             f"{gold['agree']}/{gold['total']}" if gold.get("exists") else "golden.csv 없음", "10개 중 ≥ 9", "사용자 제공"),
        gate(7, "승인", True if sc.get("approved") else None,
             (sc.get("approval") or {}).get("value", "대기"), "사용자", "사용자"),
    ]

    alerts = []
    for p in parts:
        for kind, v, msg in p["issues"][:20]:
            alerts.append({"level": "error", "where": p["part"], "voc_id": v, "msg": f"[{kind}] {msg}"})
    for b in sorted(set(batches) - covered):
        alerts.append({"level": "warn", "where": f"part_{b}", "voc_id": "-", "msg": "part 파일 없음 (분류 대기)"})
    if stale:
        alerts.append({"level": "warn", "where": "scorecard", "voc_id": "-", "msg": "채점 이후 part 파일이 바뀜 → review-grader 재채점 필요"})
    if not gold.get("exists"):
        alerts.append({"level": "info", "where": "golden", "voc_id": "-", "msg": "ax/demo/golden.csv (voc_id,tag 10행) 필요"})

    passed = sum(g["state"] == "PASS" for g in gates)
    return {
        "generated_ts": now, "active_window": ACTIVE_WINDOW,
        "active_stages": sorted(active), "root": ROOT, "allowed_tags": allowed, "definition": def_path,
        "summary": {"total": total, "expected": len(texts), "tags": {t: tags.get(t, 0) for t in allowed},
                    "review": review_n, "review_ratio": review_n / max(total, 1), "review_reason_missing": review_reason_missing,
                    "gates_passed": passed, "gates_total": len(gates),
                    "overall": "PASS" if passed == len(gates) else ("FAIL" if any(g["state"] == "FAIL" for g in gates) else "WAIT")},
        "channels": {"machine": machine, "grader": sc.get("scores", {}), "grader_title": sc.get("title", ""), "min": SCORE_MIN},
        "gates": gates, "parts": [{k: v for k, v in p.items() if k != "issues"} | {"issue_count": len(p["issues"])} for p in parts],
        "golden": gold, "events": events, "alerts": alerts,
    }


def save(status):
    data = json.dumps(status, ensure_ascii=False, indent=1)
    for name, content in (("status.json", data), ("status.js", "window.STATUS = " + data + ";\n")):
        tmp = os.path.join(BOARD, name + ".tmp")
        open(tmp, "w", encoding="utf-8").write(content)
        os.replace(tmp, os.path.join(BOARD, name))


def log_check(status):
    """관제 실행 결과를 기존 훅 기록기로 events.jsonl 에 남긴다 (ts 자동)."""
    if not os.path.exists(LOGGER):
        return
    s = status["summary"]
    rec = {"hook_event_name": "ControlCheck", "agent": "board/control.py", "overall": s["overall"],
           "gates": {g["name"]: g["state"] for g in status["gates"]}, "review": s["review"], "total": s["total"]}
    subprocess.run([sys.executable, LOGGER], input=json.dumps(rec, ensure_ascii=False).encode("utf-8"),
                   env={**os.environ, "VOC_PROJECT_ROOT": ROOT}, check=False)


def mark_stage(stage, state, note):
    """단계 진행 중 직접 표시: events.jsonl 에 StageMark 기록 (ts 자동)."""
    rec = {"hook_event_name": "StageMark", "stage": stage, "state": state, "note": note}
    subprocess.run([sys.executable, LOGGER], input=json.dumps(rec, ensure_ascii=False).encode("utf-8"),
                   env={**os.environ, "VOC_PROJECT_ROOT": ROOT}, check=False)
    print(f"StageMark {stage} {state} {note}")


def main():
    ap = argparse.ArgumentParser(description="VOC 분류 관제")
    ap.add_argument("--watch", type=int, default=0, metavar="SEC", help="SEC초마다 반복 점검")
    ap.add_argument("--open", action="store_true", help="관제 화면(board/index.html) 열기")
    ap.add_argument("--no-log", action="store_true", help="events.jsonl 기록 생략")
    ap.add_argument("--mark", nargs=2, metavar=("STAGE", "start|end"), help="단계 진행 중 직접 표시 후 종료")
    ap.add_argument("--note", default="", help="--mark 와 함께 남길 설명")
    a = ap.parse_args()

    if a.mark:
        mark_stage(int(a.mark[0]), a.mark[1], a.note)
        return

    last_sig = None
    opened = False
    while True:
        st = run()
        save(st)
        sig = (st["summary"]["overall"], tuple(g["state"] for g in st["gates"]), st["summary"]["total"], st["summary"]["review"])
        if not a.no_log and sig != last_sig:  # 상태가 바뀔 때만 기록 (watch 중 로그 폭주 방지)
            log_check(st)
        last_sig = sig
        s = st["summary"]
        print(time.strftime("%H:%M:%S"), f"[{s['overall']}] 게이트 {s['gates_passed']}/{s['gates_total']} · "
              f"{s['total']}행 · 검토 {s['review']} ({s['review_ratio']:.1%}) · "
              + " ".join(f"{g['no']}:{g['state']}{'*' if g['active'] else ''}" for g in st["gates"])
              + (f" · 진행 중 {st['active_stages']}" if st["active_stages"] else ""), flush=True)
        if a.open and not opened:
            webbrowser.open("file:///" + os.path.join(BOARD, "index.html").replace("\\", "/")); opened = True
        if not a.watch:
            break
        try:
            time.sleep(a.watch)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
