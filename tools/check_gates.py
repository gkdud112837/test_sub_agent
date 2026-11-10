"""VOC 분류 결과 품질 게이트 점검 (관제 화면 텍스트 출력).

사용: python -I -X utf8 tools/check_gates.py [output/voc_tags.csv] [golden.csv]
- golden.csv(선택): 사용자가 제공한 정답 10행 (voc_id,tag)
"""
import csv, os, re, sys, glob, collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = ["P1", "P2", "P3", "H1", "H2", "해당없음", "검토"]
REVIEW_MAX = 0.05
SCORE_MIN = 89


def load_archive():
    meta_path = glob.glob(os.path.join(BASE, "archive-*", "archive", "metadata.csv"))[0]
    root = os.path.dirname(meta_path)
    meta = list(csv.DictReader(open(meta_path, encoding="utf-8-sig")))
    files = {os.path.basename(p)[:-3]: p for p in glob.glob(os.path.join(root, "batch*", "*.md"))}
    texts = {v: open(p, encoding="utf-8").read().split("---", 2)[2].strip() for v, p in files.items()}
    return meta, texts


def main():
    out_csv = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "output", "voc_tags.csv")
    golden = sys.argv[2] if len(sys.argv) > 2 else None
    meta, texts = load_archive()
    rows = list(csv.DictReader(open(out_csv, encoding="utf-8-sig")))
    n = len(rows)

    # 1. 범위 점수 — ID 누락 · 중복
    expected = {m["voc_id"] for m in meta} | set(texts)
    ids = [r["voc_id"] for r in rows]
    dup = [k for k, c in collections.Counter(ids).items() if c > 1]
    missing = sorted(expected - set(ids))
    extra = sorted(set(ids) - expected)
    nums = sorted(int(re.sub(r"\D", "", v)) for v in expected)
    gaps = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
    bad1 = len(dup) + len(missing) + len(extra)
    s_range = round(100 * (1 - bad1 / max(len(expected), 1)))

    # 2. 근거 판정 — 모든 행 원문 그대로 인용, 15자 이내, 근거유무=Y
    bad_quote = [r["voc_id"] for r in rows
                 if not r.get("quote") or len(r["quote"]) > 15
                 or r["quote"] not in texts.get(r["voc_id"], "")
                 or r.get("근거유무") != "Y"]
    s_ground = round(100 * (1 - len(bad_quote) / max(n, 1)))

    # 3. 상식 점수 — 허용 태그 7개 + 검토 비율 · 이유
    bad_tag = [r["voc_id"] for r in rows if r["tag"] not in ALLOWED]
    review = [r for r in rows if r["tag"] == "검토"]
    no_reason = [r["voc_id"] for r in review if not r.get("note", "").strip()]
    ratio = len(review) / max(n, 1)
    s_sense = round(100 * (1 - (len(bad_tag) + len(no_reason)) / max(n, 1)))

    # 4. 골든셋 동의
    agree = None
    if golden:
        g = {r["voc_id"]: r["tag"] for r in csv.DictReader(open(golden, encoding="utf-8-sig"))}
        mine = {r["voc_id"]: r["tag"] for r in rows}
        agree = sum(mine.get(k) == v for k, v in g.items()), len(g)

    tags = collections.Counter(r["tag"] for r in rows)
    ok = lambda b: "PASS" if b else "FAIL"
    print("=" * 56)
    print(" VOC 분류 관제 화면")
    print("=" * 56)
    print(f" 전체 {n}건 | " + " · ".join(f"{t} {tags.get(t, 0)}" for t in ALLOWED))
    print(f" [검토] {len(review)}건 ({ratio:.1%}) / 한도 5% · 이유 누락 {len(no_reason)}건  {ok(ratio <= REVIEW_MAX and not no_reason)}")
    print("-" * 56)
    print(" [채점 채널]                      점수   기준   결과")
    print(f"  ① 범위 점수 (ID 누락·중복)     {s_range:>4}   ≥{SCORE_MIN}   {ok(s_range >= SCORE_MIN)}")
    print(f"     누락 {missing or '없음'} · 중복 {dup or '없음'} · 초과 {extra or '없음'} · 번호 공백 {gaps or '없음'}")
    print(f"  ② 근거 판정 (원문 인용·근거)   {s_ground:>4}   ≥{SCORE_MIN}   {ok(s_ground >= SCORE_MIN)}")
    print(f"     불량 {bad_quote[:10] or '없음'}")
    print(f"  ③ 상식 점수 (허용 태그 7개)    {s_sense:>4}   ≥{SCORE_MIN}   {ok(s_sense >= SCORE_MIN)}")
    print(f"     허용 밖 태그 {bad_tag[:10] or '없음'}")
    print("-" * 56)
    if agree:
        print(f" [골든셋] {agree[0]}/{agree[1]} 동의 (기준 9/10)  {ok(agree[0] >= 9)}")
    else:
        print(" [골든셋] 대기 — 사용자 제공 10행 필요")
    print(" [승인] 대기 — 사용자 승인 필요 (Claude는 승인하지 않음)")
    print("=" * 56)


if __name__ == "__main__":
    main()
