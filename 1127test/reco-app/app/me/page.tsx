// 내 주문 · 내 설문 — publishable 키 + 로그인 세션으로 조회. 본인 행만 오는 것은 RLS 정책이 보장한다.
import Link from "next/link";
import { createSessionClient } from "@/lib/supabase/server";
import { hasPublicEnv } from "@/lib/env";
import SignOut from "@/components/SignOut";

export const dynamic = "force-dynamic";

type OrderRow = { id: number; qty: number; ordered_at: string; products: { name: string } | null };

export default async function MePage() {
  if (!hasPublicEnv()) return <p className="msg err">환경변수가 설정되지 않았어요.</p>;
  const supabase = await createSessionClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return (
      <section>
        <h1>내 주문</h1>
        <p className="muted">로그인하면 내 주문을 볼 수 있어요. <Link href="/login">로그인</Link></p>
      </section>
    );
  }

  // where user_id = 내 id 를 쓰지 않아도 RLS가 본인 행만 돌려준다 (정책 확인용으로 일부러 필터 없음)
  const [{ data: orders, error }, { count: surveyCount, error: surveyErr }] = await Promise.all([
    supabase.from("orders").select("id,qty,ordered_at,products(name)").order("ordered_at", { ascending: false }).limit(50),
    supabase.from("surveys").select("id", { count: "exact", head: true }),
  ]);

  return (
    <section>
      <h1>내 주문</h1>
      <p className="muted">{user.email} · 설문 {surveyErr ? "-" : (surveyCount ?? 0)}회 <SignOut /></p>
      {error && <p className="msg err">주문을 불러오지 못했어요.</p>}
      {!error && (orders?.length ?? 0) === 0 && <p className="muted">아직 주문이 없어요.</p>}
      {!!orders?.length && (
        <table>
          <thead><tr><th>시각(한국)</th><th>상품</th><th>수량</th></tr></thead>
          <tbody>
            {(orders as unknown as OrderRow[]).map((o) => (
              <tr key={o.id}>
                <td>{new Date(o.ordered_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}</td>
                <td>{o.products?.name ?? "-"}</td>
                <td>{o.qty}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
