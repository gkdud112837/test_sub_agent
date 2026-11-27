// POST /api/orders — 주문 버튼. 입력 검증 → 로그인 사용자 확인 → place_order(재고 차감 + 기록, source=team)
import { NextResponse } from "next/server";
import { parseOrder } from "@/lib/validate";
import { getUserId } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { fail, isSameSiteJson, readJson } from "@/lib/http";
import { clientKey, rateLimit } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";

// 레이트 리밋: 로그인 분당 20회, 비로그인 분당 5회 · 비로그인은 1회 최대 3개 (review_v1 #3)
const LIMIT_USER = 20, LIMIT_ANON = 5, ANON_MAX_QTY = 3;

export async function POST(req: Request) {
  if (!isSameSiteJson(req)) return fail(415, "BAD_REQUEST", "잘못된 요청이에요.");
  const parsed = parseOrder(await readJson(req));
  if (!parsed.ok) return fail(400, parsed.error, "주문 정보를 다시 확인해 주세요.");
  const { productId, qty, surveyId } = parsed.value;

  try {
    const userId = await getUserId(); // 비로그인 주문은 null
    const wait = rateLimit(clientKey(req, "orders", userId), userId ? LIMIT_USER : LIMIT_ANON, 60_000);
    if (wait) return fail(429, "RATE_LIMITED", `잠시 후(${wait}초) 다시 시도해 주세요.`, { "Retry-After": String(wait) });
    if (!userId && qty > ANON_MAX_QTY) return fail(400, "BAD_QTY", `로그인하지 않으면 한 번에 ${ANON_MAX_QTY}개까지 주문할 수 있어요.`);

    const admin = createAdminClient();

    // 설문 연결은 로그인 사용자의 본인 설문만 (review_v1 #10 — 비로그인 설문은 소유를 증명할 수 없어 연결하지 않음)
    let linkedSurvey: number | null = null;
    if (surveyId && userId) {
      const { data: s } = await admin.from("surveys").select("user_id").eq("id", surveyId).maybeSingle();
      if (s?.user_id === userId) linkedSurvey = surveyId;
    }

    const { data, error } = await admin.rpc("place_order", {
      p_product_id: productId,
      p_qty: qty,
      p_user_id: userId,
      p_survey_id: linkedSurvey,
    });
    if (error) {
      if (error.message?.includes("NO_PRODUCT")) return fail(404, "NO_PRODUCT", "없는 상품이에요.");
      if (error.message?.includes("OUT_OF_STOCK")) return fail(409, "OUT_OF_STOCK", "재고가 부족해요.");
      if (error.message?.includes("INVALID_QTY")) return fail(400, "BAD_QTY", "수량은 1~20개만 가능해요.");
      throw new Error(`place_order:${error.code}`);
    }
    return NextResponse.json({ ok: true, orderId: data?.id, loggedIn: Boolean(userId) });
  } catch (e) {
    console.error("[orders]", e instanceof Error ? e.message : e);
    return fail(500, "SERVER_ERROR", "주문을 기록하지 못했어요. 잠시 후 다시 시도해 주세요.");
  }
}
