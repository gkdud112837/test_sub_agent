// 홈: 상품 목록(DB에서 읽기, publishable 키 + RLS) + 설문 → 추천 → 주문
import { createSessionClient } from "@/lib/supabase/server";
import { hasPublicEnv } from "@/lib/env";
import RecommendForm from "@/components/RecommendForm";
import type { Product } from "@/lib/types";

export const dynamic = "force-dynamic"; // 재고가 바뀌므로 매 요청마다 DB에서 읽는다

async function loadProducts(): Promise<{ products: Product[]; error: string | null }> {
  if (!hasPublicEnv()) return { products: [], error: "환경변수가 설정되지 않았어요. (.env.example 참고)" };
  try {
    const supabase = await createSessionClient();
    const { data, error } = await supabase
      .from("products")
      .select("id,name,category,tags,portion,price,stock")
      .order("category")
      .order("id");
    if (error) return { products: [], error: "상품을 불러오지 못했어요." };
    return { products: (data ?? []) as Product[], error: null };
  } catch {
    return { products: [], error: "상품을 불러오지 못했어요." };
  }
}

export default async function Home() {
  const { products, error } = await loadProducts();
  return (
    <>
      <h1>오늘 뭐 해 먹지?</h1>
      <p className="muted">세 가지만 고르면 재고가 있는 상품 중 3개를 골라 이유와 함께 보여 드려요.</p>

      <RecommendForm />

      <h2>전체 상품 {products.length ? `(${products.length})` : ""}</h2>
      {error && <p className="msg err">{error}</p>}
      {!error && products.length === 0 && <p className="muted">상품이 없어요. (RLS 읽기 정책 · GRANT 확인)</p>}
      <div className="grid">
        {products.map((p) => (
          <div key={p.id} className={`card ${p.stock === 0 ? "soldout" : ""}`}>
            <div className="name">{p.name}</div>
            <div className="meta">{p.category} · {p.portion} · {p.price.toLocaleString()}원</div>
            <div className="meta">{p.stock === 0 ? "품절" : `재고 ${p.stock}`}</div>
          </div>
        ))}
      </div>
    </>
  );
}
