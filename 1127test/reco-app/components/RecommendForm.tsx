"use client";
// 설문 → /api/recommend → 추천 카드 → 주문 버튼(/api/orders)
// 이 파일은 브라우저 코드다: 비밀 키·secret 클라이언트를 import 하지 않는다.
import { useState } from "react";
import { BUDGETS, CATEGORIES, COOKINGS, HOUSEHOLDS, type Recommendation } from "@/lib/types";

type OrderState = { qty: number; status: "idle" | "sending" | "done" | "error"; msg?: string };

export default function RecommendForm() {
  const [household, setHousehold] = useState<string>("1인");
  const [categories, setCategories] = useState<string[]>(["채소"]);
  const [budget, setBudget] = useState<number>(10000);
  const [cooking, setCooking] = useState<string>("간편");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [surveyId, setSurveyId] = useState<number | null>(null);
  const [items, setItems] = useState<Recommendation[] | null>(null);
  const [orders, setOrders] = useState<Record<number, OrderState>>({});

  const toggleCat = (c: string) =>
    setCategories((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : prev.length >= 3 ? prev : [...prev, c]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (categories.length === 0) { setError("선호 분류를 하나 이상 골라 주세요."); return; }
    setLoading(true); setError(null); setItems(null); setOrders({});
    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ household, categories, budget, cooking, note: note.trim() || null }),
      });
      const json = await res.json();
      if (!json.ok) { setError(json.message ?? "추천을 불러오지 못했어요."); return; }
      setSurveyId(json.surveyId);
      setItems(json.items);
    } catch {
      setError("네트워크 오류예요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  async function order(productId: number) {
    const qty = orders[productId]?.qty ?? 1;
    setOrders((o) => ({ ...o, [productId]: { qty, status: "sending" } }));
    try {
      const res = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ productId, qty, surveyId }),
      });
      const json = await res.json();
      setOrders((o) => ({
        ...o,
        [productId]: json.ok
          ? { qty, status: "done", msg: json.loggedIn ? "주문을 기록했어요. (내 주문에서 확인)" : "주문을 기록했어요. (비로그인 주문)" }
          : { qty, status: "error", msg: json.message ?? "주문을 기록하지 못했어요." },
      }));
    } catch {
      setOrders((o) => ({ ...o, [productId]: { qty, status: "error", msg: "네트워크 오류예요." } }));
    }
  }

  return (
    <section>
      <form onSubmit={submit}>
        <fieldset>
          <legend>몇 명이 먹나요?</legend>
          {HOUSEHOLDS.map((h) => (
            <label key={h} className="opt">
              <input type="radio" name="household" checked={household === h} onChange={() => setHousehold(h)} /> {h}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>좋아하는 분류 (최대 3개)</legend>
          {CATEGORIES.map((c) => (
            <label key={c} className="opt">
              <input type="checkbox" checked={categories.includes(c)} onChange={() => toggleCat(c)} /> {c}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>1개당 예산 · 조리</legend>
          {BUDGETS.map((b) => (
            <label key={b} className="opt">
              <input type="radio" name="budget" checked={budget === b} onChange={() => setBudget(b)} /> {b.toLocaleString()}원 이하
            </label>
          ))}
          <br />
          {COOKINGS.map((c) => (
            <label key={c} className="opt">
              <input type="radio" name="cooking" checked={cooking === c} onChange={() => setCooking(c)} /> {c}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>메모 (선택, 200자 이하 · 추천 계산에는 쓰지 않아요)</legend>
          <textarea maxLength={200} rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="예: 아침 샐러드" />
        </fieldset>
        <button type="submit" disabled={loading}>{loading ? "고르는 중…" : "추천 받기"}</button>
        {error && <p className="msg err">{error}</p>}
      </form>

      {items && (
        <>
          <h2>오늘의 추천</h2>
          {items.length === 0 && <p className="muted">조건에 맞는 재고 상품이 없어요. 예산이나 분류를 바꿔 보세요.</p>}
          <div className="grid">
            {items.map(({ product: p, reason, reasonSource }) => {
              const st = orders[p.id] ?? { qty: 1, status: "idle" };
              return (
                <div key={p.id} className="card">
                  <div className="name">{p.name}</div>
                  <div className="meta">{p.category} · {p.portion} · {p.price.toLocaleString()}원 · 재고 {p.stock}</div>
                  <p className="reason">{reason} <span className="tag">{reasonSource === "ai" ? "AI 사유" : "기본 문구"}</span></p>
                  <input
                    type="number" min={1} max={Math.min(20, p.stock)} value={st.qty} aria-label="수량"
                    onChange={(e) => setOrders((o) => ({ ...o, [p.id]: { ...st, qty: Math.max(1, Math.min(20, Number(e.target.value) || 1)) } }))}
                  />{" "}
                  <button type="button" className="ghost" disabled={st.status === "sending"} onClick={() => order(p.id)}>
                    {st.status === "sending" ? "기록 중…" : "주문"}
                  </button>
                  {st.msg && <p className={`msg ${st.status === "error" ? "err" : ""}`}>{st.msg}</p>}
                </div>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
