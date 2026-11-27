"""보충 교재 「물류 데이터 통계 분석 실습」 재현 스크립트.

실행: python -I logistics_analysis/reproduce.py  (1127test 폴더에서)
입력: 목업_데이터셋_물류.xlsx (가상 데이터) · 출력: 콘솔 + logistics_analysis/results.json
교재 부록 코드를 따르되, 교재 수치와 비교하는 assert 성격의 출력을 붙였다.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

HERE = Path(__file__).resolve().parent
XLSX = next(HERE.parent.glob("*.xlsx"))
out: dict = {}

L = pd.read_excel(XLSX, sheet_name="물류회사 데이터셋")
L["지연"] = L["배송상태"].str.contains("지연").astype(int)
L["악천후"] = (L["기상상황설명"] != "정상").astype(int)

# ── 준비: 한 행의 의미 · 정의 확인 ─────────────────────────────
wrong = L["주문 매출"].sum()
right = L.groupby("주문번호")["주문 매출"].first().sum()
legs = L.groupby("주문번호").size().value_counts().to_dict()
delay_by_days = int((L["실제구간별배송소요일"] > L["예상구간별배송소요일"]).sum())
out["준비"] = {
    "행": len(L), "주문": L["주문번호"].nunique(), "주문당구간수": {int(k): int(v) for k, v in legs.items()},
    "지연행": int(L["지연"].sum()), "지연율": round(L["지연"].mean(), 4),
    "지연=실제>예상 일치": delay_by_days == int(L["지연"].sum()),
    "악천후행": int(L["악천후"].sum()),
    "매출_잘못(억)": round(wrong / 1e8, 1), "매출_올바름(억)": round(right / 1e8, 1),
    "부풀림배수": round(wrong / right, 2),
    "주문연도별행수": L["주문일자"].dt.year.value_counts().sort_index().to_dict(),
}

# ── 실습 1: 교차표 · 카이제곱 · 크라메르 V ─────────────────────
ct = pd.crosstab(L["기상상황설명"], L["지연"])
chi2, p, dof, exp = stats.chi2_contingency(ct.values)
rate = L.groupby("기상상황설명")["지연"].agg(["size", "sum", "mean"])
bad = L[L["악천후"] == 1]
out["실습1"] = {
    "기상별": {k: {"구간": int(r["size"]), "지연": int(r["sum"]), "지연율": round(r["mean"], 3)} for k, r in rate.iterrows()},
    "chi2": round(chi2, 1), "dof": int(dof), "p": float(p),
    "cramers_v": round(float(np.sqrt(chi2 / ct.values.sum())), 3),
    "최소기대건수": round(float(exp.min()), 1),
    "악천후지연율": round(bad["지연"].mean(), 3), "정상지연율": round(L[L["악천후"] == 0]["지연"].mean(), 3),
    "악천후지연의몫": round(bad["지연"].sum() / L["지연"].sum(), 3),
}

# ── 실습 2: 구간별 층화 ───────────────────────────────────────
s2 = {}
for seg, d in L.groupby("구간"):
    c = pd.crosstab(d["악천후"], d["지연"])
    m = d.groupby("악천후")["지연"].agg(["size", "mean"])
    s2[seg] = {"정상n": int(m.loc[0, "size"]), "정상": round(m.loc[0, "mean"], 3),
               "악천후n": int(m.loc[1, "size"]), "악천후": round(m.loc[1, "mean"], 3),
               "차이%p": round((m.loc[1, "mean"] - m.loc[0, "mean"]) * 100, 1),
               "p": round(float(stats.chi2_contingency(c.values)[1]), 3)}
normal = L[L["악천후"] == 0]
p_seg_normal = stats.chi2_contingency(pd.crosstab(normal["구간"], normal["지연"]).values)[1]
out["실습2"] = {"구간별": s2, "정상기상만_구간차이_p": round(float(p_seg_normal), 2)}

# ── 실습 3: 선사별 윌슨 신뢰구간 · 전체 검정 ───────────────────
def wilson(k, n, z=1.96):
    ph = k / n; d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return c - h, c + h

S = L[L["구간"] == "선사"]
r = S.groupby("운송업체")["지연"].agg(["size", "sum", "mean"]).sort_values("mean")
lo, hi = wilson(r["sum"], r["size"])
p5 = stats.chi2_contingency(pd.crosstab(S["운송업체"], S["지연"]).values)[1]
normal_rate = S[S["악천후"] == 0].groupby("운송업체")["지연"].mean()
out["실습3"] = {
    "선사별": {k: {"n": int(row["size"]), "지연율": round(row["mean"], 3),
                 "CI": [round(float(lo[k]), 3), round(float(hi[k]), 3)],
                 "정상기상만": round(float(normal_rate[k]), 3)} for k, row in r.iterrows()},
    "전체검정_p": round(float(p5), 2),
}

# ── 실습 4: 예측 모델 (주문번호 단위 분리) ─────────────────────
L["월"] = L["주문일자"].dt.month
cat = ["구간", "주문국가", "운송업체", "기상상황설명", "상품카테고리", "고객유형"]
num = ["월", "상품주문수량", "예상구간별배송소요일"]
X, y = L[cat + num], L["지연"]
tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, L["주문번호"]))
yt = y.iloc[te]

def pipe(model):
    pre = ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore"), cat), ("n", StandardScaler(), num)])
    return Pipeline([("p", pre), ("m", model)])

models = {
    "로지스틱 회귀": LogisticRegression(max_iter=1000),
    "의사결정나무(깊이4)": DecisionTreeClassifier(max_depth=4, random_state=0),
    "그래디언트 부스팅": GradientBoostingClassifier(random_state=0),
    "의사결정나무(무제한)": DecisionTreeClassifier(random_state=0),
}
s4 = {"분리": {"학습": len(tr), "검증": len(te), "검증지연": int(yt.sum())},
      "기준선": round(1 - yt.mean(), 3)}
rule = ((L["구간"] == "선사") & (L["악천후"] == 1)).astype(int).iloc[te]
s4["규칙하나"] = {"acc": round(accuracy_score(yt, rule), 3), "prec": round(precision_score(yt, rule), 3),
                 "rec": round(recall_score(yt, rule), 3)}
fitted = {}
for name, m in models.items():
    pl = pipe(m).fit(X.iloc[tr], y.iloc[tr]); fitted[name] = pl
    pred = pl.predict(X.iloc[te])
    s4[name] = {"train_acc": round(accuracy_score(y.iloc[tr], pl.predict(X.iloc[tr])), 3),
                "acc": round(accuracy_score(yt, pred), 3),
                "prec": round(precision_score(yt, pred, zero_division=0), 3),
                "rec": round(recall_score(yt, pred), 3)}
gb = fitted["그래디언트 부스팅"]
prob = gb.predict_proba(X.iloc[te])[:, 1]
s4["GB_AUC"] = round(roc_auc_score(yt, prob), 3)
s4["경보기준"] = {str(t): {"경보": int((prob >= t).sum()),
                          "prec": round(precision_score(yt, (prob >= t).astype(int)), 3),
                          "rec": round(recall_score(yt, (prob >= t).astype(int)), 3)} for t in (0.3, 0.4, 0.5, 0.7)}
# 정답 누설 실험
for leak in ["실제구간별배송소요일", "배송지연코드"]:
    is_num = pd.api.types.is_numeric_dtype(L[leak])  # pandas 3은 문자열 열이 object가 아니라 str
    cat_l = cat + ([] if is_num else [leak])
    num_l = num + ([leak] if is_num else [])
    pre = ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore"), cat_l), ("n", StandardScaler(), num_l)])
    pl = Pipeline([("p", pre), ("m", GradientBoostingClassifier(random_state=0))]).fit(L[cat_l + num_l].iloc[tr], y.iloc[tr])
    s4[f"누설_{leak}"] = round(accuracy_score(yt, pl.predict(L[cat_l + num_l].iloc[te])), 3)
out["실습4"] = s4

# ── 실습 5: 주문 단위 분위수 · 준수율 ─────────────────────────
O = (L.groupby("주문번호").agg(국가=("주문국가", "first"), 요청=("주문 시 배송요청", "first"),
                              실제=("총실제소요일", "first")).reset_index())
O["요청일"] = O["요청"].str.extract(r"(\d+)").astype(int)
O["준수"] = (O["요청일"] >= O["실제"]).astype(int)
q = O["실제"].quantile([.25, .5, .75, .9])
by = O.groupby("국가").agg(n=("실제", "size"), 평균=("실제", "mean"), 최소=("실제", "min"),
                          p10=("실제", lambda s: s.quantile(.1)), p90=("실제", lambda s: s.quantile(.9)),
                          준수율=("준수", "mean")).sort_values("평균")
pv = O.pivot_table(index="국가", columns="요청일", values="준수", aggfunc="mean")
out["실습5"] = {
    "전체": {"평균": round(O["실제"].mean(), 1), "중앙값": float(q[.5]), "p25": float(q[.25]), "p75": float(q[.75]),
             "p90": float(q[.9]), "최소": int(O["실제"].min()), "최대": int(O["실제"].max()),
             "표준편차": round(O["실제"].std(), 1), "준수율": round(O["준수"].mean(), 3)},
    "국가별": {k: {"n": int(r_["n"]), "평균": round(r_["평균"], 1), "최소": int(r_["최소"]),
                 "p10~p90": [float(r_["p10"]), float(r_["p90"])], "준수율": round(r_["준수율"], 3),
                 **{f"D+{c}": (None if pd.isna(pv.loc[k, c]) else round(float(pv.loc[k, c]), 3)) for c in pv.columns}}
             for k, r_ in by.iterrows()},
}

(HERE / "results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
