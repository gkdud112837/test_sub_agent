"""목업_데이터셋_물류.xlsx → 분류별로 정리한 물류_데이터셋_정리본.xlsx

실행: python -I logistics_analysis/build_tidy_workbook.py   (1127test 폴더에서)
원본은 수정하지 않는다. 원본 값은 그대로 옮기고, 계산 열·요약은 엑셀 수식으로 넣는다.
"""
import glob
import os
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
SRC = next(p for p in glob.glob("*.xlsx") if "정리본" not in p)
OUT = ROOT / "물류_데이터셋_정리본.xlsx"

L = pd.read_excel(SRC, sheet_name="물류회사 데이터셋")
L = L.sort_values(["주문번호", "운송번호"]).reset_index(drop=True)

# 원본에서 확인한 사실을 다시 확인 (정리 규칙의 근거)
assert (L["매출"] == L["물류비 총매출"]).all() and (L["매출"] == L["총매출"]).all()
assert (L["물류비 수익"] == L["수익"]).all() and (L["수익"] == L["매출"] - L["매입"]).all()

# ── 스타일 ───────────────────────────────────────────────────────
FONT = "Arial"
GROUP_COLORS = {  # 분류 띠(진한색) / 헤더(연한색)
    "blue": ("1F4E78", "DDEBF7"), "green": ("375623", "E2EFDA"), "gold": ("7F6000", "FFF2CC"),
    "orange": ("843C0C", "FCE4D6"), "purple": ("3F3151", "E4DFEC"), "teal": ("0B5563", "D9F0F2"),
    "gray": ("3A3A3A", "EDEDED"),
}
thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
F_BODY = Font(name=FONT, size=10)
F_BOLD = Font(name=FONT, size=10, bold=True)
F_TITLE = Font(name=FONT, size=14, bold=True)
F_NOTE = Font(name=FONT, size=9, italic=True, color="595959")
FMT = {"int": "#,##0", "won": "#,##0", "pct": "0.0%", "dt": "yyyy-mm-dd hh:mm", "day": "0", "geo": "0.00000",
       "txt": "@", "year": "0"}

wb = Workbook()
wb.remove(wb.active)


def write_table(ws, groups, rows, start_row=1, widths=None):
    """groups: [(분류명, 색, [(헤더, 형식, 너비), ...]), ...]
    rows: 행 리스트. 각 값은 숫자/문자/날짜, 또는 {r}을 행 번호로 바꿀 수식 문자열('=...')."""
    band, head, first = start_row, start_row + 1, start_row + 2
    col = 1
    cols = []
    for gname, color, fields in groups:
        dark, light = GROUP_COLORS[color]
        c0 = col
        for h, fmt, w in fields:
            cell = ws.cell(head, col, h)
            cell.font = Font(name=FONT, size=10, bold=True, color="000000")
            cell.fill = PatternFill("solid", fgColor=light)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = BORDER
            ws.column_dimensions[get_column_letter(col)].width = w
            cols.append(fmt)
            col += 1
        ws.merge_cells(start_row=band, start_column=c0, end_row=band, end_column=col - 1)
        b = ws.cell(band, c0, gname)
        b.font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
        b.fill = PatternFill("solid", fgColor=dark)
        b.alignment = Alignment(horizontal="center", vertical="center")
        for cc in range(c0, col):
            ws.cell(band, cc).fill = PatternFill("solid", fgColor=dark)
    ws.row_dimensions[head].height = 30
    for i, row in enumerate(rows):
        r = first + i
        for j, v in enumerate(row):
            if isinstance(v, str) and v.startswith("="):
                v = v.replace("{r}", str(r))
            cell = ws.cell(r, j + 1, v)
            cell.font = F_BODY
            if cols[j] in FMT:
                cell.number_format = FMT[cols[j]]
    last_col = get_column_letter(len(cols))
    ws.auto_filter.ref = f"A{head}:{last_col}{first + len(rows) - 1}"
    ws.freeze_panes = ws.cell(first, 3)
    return first, first + len(rows) - 1


# ════════════════════════════════════════════════════════════════
# 시트: 주문 (3,200행 — 주문 단위 값)
# ════════════════════════════════════════════════════════════════
O = L.groupby("주문번호", sort=True).first().reset_index()
legs = L.groupby("주문번호").size()
ws_o = wb.create_sheet("주문")
o_groups = [
    ("주문 정보", "blue", [("주문번호", "txt", 11), ("주문일자", "dt", 16), ("주문연도", "year", 8),
                          ("고객유형", "txt", 8), ("주문프로세스단계", "txt", 14)]),
    ("상품", "green", [("상품ID", "int", 8), ("상품명", "txt", 16), ("상품카테고리", "txt", 11),
                      ("카테고리ID", "int", 9), ("상품주문수량", "int", 9), ("단가(원)", "won", 11),
                      ("주문 매출(원)", "won", 13)]),
    ("배송지 · 집하", "gold", [("주문국가", "txt", 9), ("주문도시", "txt", 12), ("위도", "geo", 10),
                            ("경도", "geo", 11), ("집하지", "txt", 30), ("집하지 유형", "txt", 12)]),
    ("납기", "orange", [("주문 시 배송요청", "txt", 10), ("요청일수", "day", 8), ("총실제소요일", "day", 9),
                       ("배송일자", "dt", 16), ("여유일", "day", 8), ("납기 준수", "txt", 9)]),
    ("운송 요약 (운송구간 시트 집계)", "purple", [("구간 수", "int", 7), ("경로", "txt", 8), ("지연 구간 수", "int", 9),
                                         ("물류 매출 합(원)", "won", 13), ("물류 수익 합(원)", "won", 13)]),
]
# 열 위치: A주문번호 B주문일자 C연도 D고객 E단계 | F상품ID G상품명 H카테고리 I카테고리ID J수량 K단가 L주문매출
#          M국가 N도시 O위도 P경도 Q집하지 R집하지유형 | S요청 T요청일수 U총실제 V배송일자 W여유일 X준수
#          Y구간수 Z경로 AA지연구간수 AB물류매출 AC물류수익
o_rows = []
for _, x in O.iterrows():
    o_rows.append([
        x["주문번호"], x["주문일자"].to_pydatetime(), "=YEAR(B{r})", x["고객유형"], x["주문프로세스단계"],
        int(x["상품ID"]), x["상품명"], x["상품카테고리"], int(x["카테고리ID"]), int(x["상품주문수량"]),
        "=L{r}/J{r}", int(x["주문 매출"]),
        x["주문국가"], x["주문도시"], float(x["위도"]), float(x["경도"]), x["집하지"],
        '=IF(LEFT(Q{r},7)="Hanbit","Hanbit 해외 지사","국내 업체")',
        x["주문 시 배송요청"], "=VALUE(MID(S{r},3,3))", int(x["총실제소요일"]), x["배송일자"].to_pydatetime(),
        "=T{r}-U{r}", '=IF(W{r}>=0,"준수","미준수")',
        "=COUNTIF(운송구간!$A:$A,A{r})", '=IF(Y{r}=4,"경유","직항")',
        '=COUNTIFS(운송구간!$A:$A,A{r},운송구간!$M:$M,"배송완료(지연)")',
        "=SUMIF(운송구간!$A:$A,A{r},운송구간!$T:$T)", "=SUMIF(운송구간!$A:$A,A{r},운송구간!$U:$U)",
    ])
o_first, o_last = write_table(ws_o, o_groups, o_rows)

# ════════════════════════════════════════════════════════════════
# 시트: 운송구간 (10,000행 — 구간마다 다른 값)
# ════════════════════════════════════════════════════════════════
ws_l = wb.create_sheet("운송구간")
l_groups = [
    ("식별", "blue", [("주문번호", "txt", 11), ("운송번호", "txt", 12), ("순번", "int", 6),
                     ("주문국가 (주문 시트 참조)", "txt", 11)]),
    ("경로", "green", [("구간", "txt", 9), ("배송모드", "txt", 9), ("출발지", "txt", 32),
                      ("도착지", "txt", 16), ("운송업체", "txt", 22)]),
    ("소요일 · 상태", "gold", [("예상 소요일", "day", 8), ("실제 소요일", "day", 8), ("차이(실제−예상)", "day", 9),
                            ("배송상태", "txt", 13)]),
    ("지연 · 기상", "orange", [("배송지연코드", "txt", 9), ("배송지연코드명", "txt", 13), ("기상상황코드", "txt", 9),
                            ("기상상황설명", "txt", 10), ("악천후 여부", "txt", 9)]),
    ("금액 (원)", "purple", [("매입", "won", 11), ("매출", "won", 11), ("수익", "won", 11), ("마진율", "pct", 8)]),
    ("결제", "teal", [("매입결제방식", "txt", 20), ("매출결제방식", "txt", 20)]),
]
# A주문번호 B운송번호 C순번 D국가 | E구간 F모드 G출발 H도착 I업체 | J예상 K실제 L차이 M상태 |
# N지연코드 O코드명 P기상코드 Q기상설명 R악천후 | S매입 T매출 U수익 V마진율 | W매입결제 X매출결제
l_rows = []
for _, x in L.iterrows():
    l_rows.append([
        x["주문번호"], x["운송번호"], int(x["운송번호"].rsplit("-", 1)[1]),
        f"=INDEX(주문!$M${o_first}:$M${o_last},MATCH(A{{r}},주문!$A${o_first}:$A${o_last},0))",
        x["구간"], x["배송모드"], x["출발지"], x["도착지"], x["운송업체"],
        int(x["예상구간별배송소요일"]), int(x["실제구간별배송소요일"]), "=K{r}-J{r}", x["배송상태"],
        x["배송지연코드"], x["배송지연코드명"] if pd.notna(x["배송지연코드명"]) else "(지연 없음)",
        x["기상상황코드"], x["기상상황설명"], '=IF(P{r}="N","정상","악천후")',
        int(x["매입"]), int(x["매출"]), "=T{r}-S{r}", "=IF(T{r}=0,0,U{r}/T{r})",
        x["매입결제방식"], x["매출결제방식"],
    ])
l_first, l_last = write_table(ws_l, l_groups, l_rows)
LR = f"${l_first}:$"  # unused helper

# ════════════════════════════════════════════════════════════════
# 마스터: 상품 · 지역 · 코드표
# ════════════════════════════════════════════════════════════════
OA, OL = f"주문!$A${o_first}:$A${o_last}", o_last
def ocol(c): return f"주문!${c}${o_first}:${c}${o_last}"
def lcol(c): return f"운송구간!${c}${l_first}:${c}${l_last}"

ws_p = wb.create_sheet("상품")
prod = O.assign(단가=O["주문 매출"] / O["상품주문수량"]).groupby(
    ["카테고리ID", "상품카테고리", "상품ID", "상품명"])["단가"].first().reset_index().sort_values(["카테고리ID", "상품ID"])
p_groups = [("분류", "green", [("카테고리ID", "int", 10), ("상품카테고리", "txt", 12)]),
            ("상품", "blue", [("상품ID", "int", 8), ("상품명", "txt", 18), ("단가(원)", "won", 11)]),
            ("주문 집계 (수식)", "purple", [("주문 수", "int", 9), ("주문 수량 합", "int", 11), ("주문 매출 합(원)", "won", 15)])]
p_rows = [[int(r["카테고리ID"]), r["상품카테고리"], int(r["상품ID"]), r["상품명"], int(r["단가"]),
           f"=COUNTIF({ocol('F')},C{{r}})", f"=SUMIF({ocol('F')},C{{r}},{ocol('J')})",
           f"=SUMIF({ocol('F')},C{{r}},{ocol('L')})"] for _, r in prod.iterrows()]
write_table(ws_p, p_groups, p_rows)

ws_g = wb.create_sheet("지역")
geo = O.groupby(["주문국가", "주문도시"]).size().reset_index()[["주문국가", "주문도시"]]
abroad = L[L["구간"] == "해외운송"].groupby("주문국가")["운송업체"].first().to_dict()
hub = O[O["집하지"].str.startswith("Hanbit")].groupby("주문국가")["집하지"].first().to_dict()
g_groups = [("지역", "gold", [("주문국가", "txt", 10), ("주문도시", "txt", 13), ("해외 도착항", "txt", 17)]),
            ("현지 업체", "teal", [("해외운송 업체", "txt", 24), ("해외 집하지(지사)", "txt", 34)]),
            ("주문 집계 (수식)", "purple", [("주문 수", "int", 8), ("주문 매출 합(원)", "won", 15),
                                          ("납기 준수 주문", "int", 10), ("납기 준수율", "pct", 9)])]
g_rows = [[r["주문국가"], r["주문도시"], f'{r["주문도시"]} Port', abroad[r["주문국가"]], hub.get(r["주문국가"], ""),
           f"=COUNTIFS({ocol('M')},A{{r}},{ocol('N')},B{{r}})",
           f"=SUMIFS({ocol('L')},{ocol('M')},A{{r}},{ocol('N')},B{{r}})",
           f'=COUNTIFS({ocol("M")},A{{r}},{ocol("N")},B{{r}},{ocol("X")},"준수")',
           "=IF(F{r}=0,0,H{r}/F{r})"] for _, r in geo.iterrows()]
gf, gl = write_table(ws_g, g_groups, g_rows)
ws_g.cell(gl + 2, 1, "국내 출발 거점 (DC → 출항항)").font = F_BOLD
dc = L[L["구간"] == "국내운송"].groupby(["출발지", "도착지"]).size().reset_index()
for i, r in dc.iterrows():
    rr = gl + 3 + i
    ws_g.cell(rr, 1, r["출발지"]).font = F_BODY
    ws_g.cell(rr, 3, r["도착지"]).font = F_BODY
    c = ws_g.cell(rr, 6, f'=COUNTIFS({lcol("G")},A{rr},{lcol("E")},"국내운송")'); c.font = F_BODY; c.number_format = "#,##0"
ws_g.cell(gl + 3 + len(dc), 1, "※ F열 = 국내운송 구간 수(= 주문 수)").font = F_NOTE

# 코드표: 여러 개의 작은 표를 세로로
ws_c = wb.create_sheet("코드표")
ws_c.column_dimensions["A"].width = 26; ws_c.column_dimensions["B"].width = 26
for col in "CDEF": ws_c.column_dimensions[col].width = 14
row = 1
def code_block(title, color, headers, data, fmts):
    global row
    dark, light = GROUP_COLORS[color]
    t = ws_c.cell(row, 1, title); t.font = Font(name=FONT, size=11, bold=True, color="FFFFFF")
    for cc in range(1, len(headers) + 1): ws_c.cell(row, cc).fill = PatternFill("solid", fgColor=dark)
    row += 1
    for j, h in enumerate(headers):
        c = ws_c.cell(row, j + 1, h); c.font = F_BOLD; c.fill = PatternFill("solid", fgColor=light); c.border = BORDER
    row += 1
    for d in data:
        for j, v in enumerate(d):
            if isinstance(v, str) and v.startswith("="): v = v.replace("{r}", str(row))
            c = ws_c.cell(row, j + 1, v); c.font = F_BODY; c.border = BORDER
            if fmts[j] in FMT: c.number_format = FMT[fmts[j]]
        row += 1
    row += 1

cnt = lambda colL, key: f'=COUNTIF({lcol(colL)},"{key}")'
code_block("기상상황 코드", "orange", ["코드", "설명", "구간 수", "지연 구간 수", "지연율"],
           [[k, v, cnt("P", k), f'=COUNTIFS({lcol("P")},A{{r}},{lcol("M")},"배송완료(지연)")', "=IF(C{r}=0,0,D{r}/C{r})"]
            for k, v in sorted(L.groupby("기상상황코드")["기상상황설명"].first().items())],
           ["txt", "txt", "int", "int", "pct"])
code_block("배송지연 코드", "orange", ["코드", "코드명", "구간 수"],
           [[k, (v if pd.notna(v) else "(지연 없음)"), cnt("N", k)]
            for k, v in sorted(L.groupby("배송지연코드")["배송지연코드명"].first().items())],
           ["txt", "txt", "int"])
code_block("배송상태 (실제 vs 예상 소요일로 결정됨)", "gold", ["배송상태", "조건", "구간 수"],
           [["배송완료", "실제 = 예상", cnt("M", "배송완료")], ["배송완료(조기)", "실제 < 예상", cnt("M", "배송완료(조기)")],
            ["배송완료(지연)", "실제 > 예상", cnt("M", "배송완료(지연)")]], ["txt", "txt", "int"])
code_block("구간", "green", ["구간", "배송모드", "구간 수", "지연 구간 수", "지연율"],
           [[g, m, cnt("E", g), f'=COUNTIFS({lcol("E")},A{{r}},{lcol("M")},"배송완료(지연)")', "=IF(C{r}=0,0,D{r}/C{r})"]
            for g, m in [("국내운송", "일반배송"), ("선사", "해운"), ("해외운송", "일반배송")]],
           ["txt", "txt", "int", "int", "pct"])
code_block("운송업체", "green", ["운송업체", "구간", "구간 수", "지연 구간 수", "지연율"],
           [[k, v, cnt("I", k), f'=COUNTIFS({lcol("I")},A{{r}},{lcol("M")},"배송완료(지연)")', "=IF(C{r}=0,0,D{r}/C{r})"]
            for k, v in sorted(L.groupby("운송업체")["구간"].first().items(), key=lambda kv: (["국내운송", "선사", "해외운송"].index(kv[1]), kv[0]))],
           ["txt", "txt", "int", "int", "pct"])
code_block("결제방식", "teal", ["결제방식", "", "매입 구간 수", "매출 구간 수"],
           [[k, "", f'=COUNTIF({lcol("W")},A{{r}})', f'=COUNTIF({lcol("X")},A{{r}})']
            for k in sorted(L["매입결제방식"].unique())], ["txt", "txt", "int", "int"])
code_block("주문프로세스단계", "blue", ["단계", "", "주문 수"],
           [[k, "", f'=COUNTIF({ocol("E")},A{{r}})'] for k in ["주문생성", "결제확인", "주문확정", "물류처리및배송중", "배송완료"]],
           ["txt", "txt", "int"])
code_block("주문 시 배송요청", "orange", ["요청", "요청일수", "주문 수", "준수 주문", "준수율"],
           [[k, int(k[2:]), f'=COUNTIF({ocol("S")},A{{r}})', f'=COUNTIFS({ocol("S")},A{{r}},{ocol("X")},"준수")',
             "=IF(C{r}=0,0,D{r}/C{r})"] for k in ["D+30", "D+45", "D+60"]], ["txt", "int", "int", "int", "pct"])
code_block("집하지", "gold", ["집하지", "유형", "주문 수"],
           [[k, ("Hanbit 해외 지사" if k.startswith("Hanbit") else "국내 업체"), f'=COUNTIF({ocol("Q")},A{{r}})']
            for k in sorted(O["집하지"].unique(), key=lambda s: (s.startswith("Hanbit"), s))], ["txt", "txt", "int"])

# ════════════════════════════════════════════════════════════════
# 분류별 요약
# ════════════════════════════════════════════════════════════════
ws_s = wb.create_sheet("분류별 요약", 0)
ws_s.column_dimensions["A"].width = 18
for col in "BCDEFG": ws_s.column_dimensions[col].width = 15
ws_s["A1"] = "분류별 요약"; ws_s["A1"].font = F_TITLE
ws_s["A2"] = "모든 숫자는 주문 · 운송구간 시트를 참조하는 수식입니다. 주문 단위 값(주문 매출 · 납기)은 주문 시트, 구간 단위 값(지연 · 물류 매출)은 운송구간 시트에서 셉니다."
ws_s["A2"].font = F_NOTE
srow = 4
def sum_block(title, color, headers, data, fmts):
    global srow
    dark, light = GROUP_COLORS[color]
    t = ws_s.cell(srow, 1, title); t.font = Font(name=FONT, size=11, bold=True, color="FFFFFF")
    for cc in range(1, len(headers) + 1): ws_s.cell(srow, cc).fill = PatternFill("solid", fgColor=dark)
    srow += 1
    for j, h in enumerate(headers):
        c = ws_s.cell(srow, j + 1, h); c.font = F_BOLD; c.fill = PatternFill("solid", fgColor=light); c.border = BORDER
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    srow += 1; top = srow
    for d in data:
        for j, v in enumerate(d):
            if isinstance(v, str) and v.startswith("="): v = v.replace("{r}", str(srow))
            c = ws_s.cell(srow, j + 1, v); c.font = F_BODY; c.border = BORDER
            if fmts[j] in FMT: c.number_format = FMT[fmts[j]]
        srow += 1
    # 합계 행
    c = ws_s.cell(srow, 1, "합계"); c.font = F_BOLD; c.border = BORDER
    for j, f in enumerate(fmts[1:], start=2):
        col = get_column_letter(j)
        if f in ("int", "won"):
            cell = ws_s.cell(srow, j, f"=SUM({col}{top}:{col}{srow - 1})")
            cell.number_format = FMT[f]
        else:
            cell = ws_s.cell(srow, j)
        cell.font = F_BOLD; cell.border = BORDER
    return top, srow

def fix_rate(top, tot, num_col, den_col, rate_col):
    c = ws_s.cell(tot, rate_col, f"=IF({get_column_letter(den_col)}{tot}=0,0,{get_column_letter(num_col)}{tot}/{get_column_letter(den_col)}{tot})")
    c.number_format = FMT["pct"]; c.font = F_BOLD

# 1) 주문 기준
order_hdr = ["", "주문 수", "주문 매출 합(원)", "납기 준수 주문", "납기 준수율"]
order_fmt = ["txt", "int", "won", "int", "pct"]
def order_rows(colL, keys):
    return [[k, f'=COUNTIF({ocol(colL)},A{{r}})', f'=SUMIF({ocol(colL)},A{{r}},{ocol("L")})',
             f'=COUNTIFS({ocol(colL)},A{{r}},{ocol("X")},"준수")', "=IF(B{r}=0,0,D{r}/B{r})"] for k in keys]
for title, colL, keys, color in [
    ("① 국가별 (주문 기준)", "M", O["주문국가"].value_counts().index.tolist(), "gold"),
    ("② 상품카테고리별 (주문 기준)", "H", sorted(O["상품카테고리"].unique()), "green"),
    ("③ 고객유형별 (주문 기준)", "D", ["B2B", "B2C"], "blue"),
    ("④ 배송요청별 (주문 기준)", "S", ["D+30", "D+45", "D+60"], "orange"),
    ("⑤ 경로별 (주문 기준)", "Z", ["직항", "경유"], "purple"),
]:
    hdr = order_hdr.copy(); hdr[0] = title.split(" ")[1]
    top, tot = sum_block(title, color, hdr, order_rows(colL, keys), order_fmt)
    fix_rate(top, tot, 4, 2, 5); srow += 2

# 연도별
yr = [[y, f'=COUNTIF({ocol("C")},A{{r}})', f'=SUMIF({ocol("C")},A{{r}},{ocol("L")})',
       f'=COUNTIFS({ocol("C")},A{{r}},{ocol("X")},"준수")', "=IF(B{r}=0,0,D{r}/B{r})"] for y in [2023, 2024, 2025]]
top, tot = sum_block("⑥ 주문연도별 (주문 기준)", "blue", ["주문연도"] + order_hdr[1:], yr, ["year"] + order_fmt[1:])
fix_rate(top, tot, 4, 2, 5); srow += 2

# 2) 구간 기준
leg_hdr = ["", "구간 수", "지연 구간 수", "지연율", "물류 매출(원)", "물류 수익(원)", "마진율"]
leg_fmt = ["txt", "int", "int", "pct", "won", "won", "pct"]
def leg_rows(colL, keys):
    return [[k, f'=COUNTIF({lcol(colL)},A{{r}})', f'=COUNTIFS({lcol(colL)},A{{r}},{lcol("M")},"배송완료(지연)")',
             "=IF(B{r}=0,0,C{r}/B{r})", f'=SUMIF({lcol(colL)},A{{r}},{lcol("T")})', f'=SUMIF({lcol(colL)},A{{r}},{lcol("U")})',
             "=IF(E{r}=0,0,F{r}/E{r})"] for k in keys]
for title, colL, keys, color in [
    ("⑦ 구간별 (운송구간 기준)", "E", ["국내운송", "선사", "해외운송"], "green"),
    ("⑧ 기상별 (운송구간 기준)", "Q", ["정상", "우천·풍랑", "강풍", "안개", "태풍"], "orange"),
    ("⑨ 선사별 (선사 구간만)", "I", sorted(L.loc[L["구간"] == "선사", "운송업체"].unique()), "teal"),
]:
    hdr = leg_hdr.copy(); hdr[0] = title.split(" ")[1]
    top, tot = sum_block(title, color, hdr, leg_rows(colL, keys), leg_fmt)
    fix_rate(top, tot, 3, 2, 4); fix_rate(top, tot, 6, 5, 7); srow += 2
ws_s.freeze_panes = "B4"

# ════════════════════════════════════════════════════════════════
# 안내
# ════════════════════════════════════════════════════════════════
ws_r = wb.create_sheet("안내", 0)
ws_r.column_dimensions["A"].width = 22; ws_r.column_dimensions["B"].width = 95
lines = [
    ("title", "물류 데이터셋 정리본"),
    ("note", f"원본: {SRC} · 시트 「물류회사 데이터셋」 10,000행 × 39열 (가상 데이터). 원본 파일은 수정하지 않았습니다."),
    ("", ""),
    ("h", "시트 구성"),
    ("분류별 요약", "국가 · 카테고리 · 고객유형 · 배송요청 · 경로 · 연도별(주문 기준), 구간 · 기상 · 선사별(구간 기준) 집계. 모두 수식"),
    ("주문", "3,200행 — 주문 하나당 한 행. 주문 단위 값 18개 + 계산 열(단가 · 요청일수 · 여유일 · 납기 준수 · 운송 요약)"),
    ("운송구간", "10,000행 — 운송 구간 하나당 한 행(원본과 같은 단위). 구간마다 달라지는 값 + 계산 열(차이 · 악천후 · 수익 · 마진율)"),
    ("상품", "상품 18개 마스터: 카테고리 · 상품ID · 단가 + 주문 집계"),
    ("지역", "국가 → 도시 → 도착항 → 해외운송 업체 → 해외 집하지, 국내 DC → 출항항"),
    ("코드표", "기상 · 지연코드 · 배송상태 · 구간 · 운송업체 · 결제방식 · 주문프로세스 · 배송요청 · 집하지 코드와 건수"),
    ("", ""),
    ("h", "정리 규칙"),
    ("1. 단위 분리", "원본은 한 행 = 운송 구간이라, 주문 단위 값(주문 매출 · 총실제소요일 · 수량 등)이 구간 행마다 3~4번 반복됐습니다. 이를 주문 시트로 떼어 내 한 번씩만 두었습니다."),
    ("2. 중복 열 제거", "「물류비 총매출」「총매출」은 「매출」과, 「물류비 수익」「수익」은 「매출−매입」과 모든 행에서 같아 뺐습니다. 수익은 수식(매출−매입)으로 넣었습니다."),
    ("3. 열 분류", "각 시트의 1행 색 띠가 분류입니다 (예: 주문 정보 · 상품 · 배송지 · 납기 · 운송 요약 / 식별 · 경로 · 소요일 · 지연 · 금액 · 결제)."),
    ("4. 값 표기", "배송지연코드 -1(지연 없음)의 빈 코드명은 「(지연 없음)」으로 채웠습니다. 다른 원본 값은 바꾸지 않았습니다."),
    ("5. 정렬", "주문번호 → 운송번호 순으로 정렬했습니다."),
    ("6. 연결 키", "주문번호로 주문 ↔ 운송구간을 연결합니다(1 : 3~4). 상품ID → 상품, 주문국가 · 주문도시 → 지역."),
    ("", ""),
    ("h", "계산 열 정의"),
    ("단가(원)", "주문 매출 ÷ 상품주문수량 (상품마다 하나로 고정된 값임을 원본에서 확인)"),
    ("요청일수 · 여유일", "「D+30」의 숫자 30 · 여유일 = 요청일수 − 총실제소요일 (0 이상이면 납기 준수)"),
    ("구간 수 · 경로", "운송구간 시트에서 같은 주문번호의 행 수 · 4이면 경유(Singapore/Kaohsiung), 3이면 직항"),
    ("지연 구간 수", "같은 주문 중 배송상태가 「배송완료(지연)」인 구간 수"),
    ("차이(실제−예상)", "양수 = 지연, 0 = 정시, 음수 = 조기 (배송상태와 100% 일치)"),
    ("악천후 여부", "기상상황코드가 N이 아니면 악천후"),
    ("", ""),
    ("h", "주의"),
    ("기간", "주문일자는 2023-01-01 ~ 2025-12-30 (보충 교재의 「2024년 주문」 설명과 다름)"),
    ("배송상태 · 지연코드", "배송이 끝난 뒤에 생기는 값이므로 지연 예측 모델의 입력으로 쓰면 정답 누설입니다."),
    ("주문프로세스단계", "배송상태는 모두 「배송완료」 계열인데 이 열에는 주문생성 · 결제확인 등이 섞여 있어 서로 맞지 않습니다."),
    ("열기", "수식은 엑셀에서 열 때 자동 계산됩니다. 필터는 각 시트 2행에 걸려 있습니다."),
]
for i, (a, b) in enumerate(lines, start=1):
    if a == "title":
        ws_r.cell(i, 1, b).font = F_TITLE
    elif a == "note":
        ws_r.cell(i, 1, b).font = F_NOTE
    elif a == "h":
        c = ws_r.cell(i, 1, b); c.font = Font(name=FONT, size=11, bold=True, color="FFFFFF")
        for cc in (1, 2): ws_r.cell(i, cc).fill = PatternFill("solid", fgColor="1F4E78")
    elif a:
        ws_r.cell(i, 1, a).font = F_BOLD
        c = ws_r.cell(i, 2, b); c.font = F_BODY; c.alignment = Alignment(wrap_text=True, vertical="top")

for ws in wb.worksheets:
    ws.sheet_view.showGridLines = ws.title in ("주문", "운송구간")
wb.calculation.fullCalcOnLoad = True  # openpyxl은 수식 결과를 저장하지 않으므로 열 때 전체 계산
wb.save(OUT)
print("saved", OUT, {ws.title: ws.max_row for ws in wb.worksheets})
