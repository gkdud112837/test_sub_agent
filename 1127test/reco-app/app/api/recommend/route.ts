// POST /api/recommend — 설문 → 입력 검증 → 상품 조회 → 룰 점수 → 설문 저장 → AI 사유(실패 시 기본 문구)
import { NextResponse } from "next/server";
import { parseSurvey } from "@/lib/validate";
import { rankProducts, fallbackReason } from "@/lib/recommend";
import { generateReasons } from "@/lib/gemini";
import { createSessionClient, getUserId } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { fail, isSameSiteJson, readJson } from "@/lib/http";
import { clientKey, rateLimit } from "@/lib/rateLimit";
import type { Product, Recommendation } from "@/lib/types";

export const dynamic = "force-dynamic";

// 레이트 리밋: 추천 1회 = surveys 1행 + Gemini 1회. 로그인 분당 10회, 비로그인 분당 5회 (review_v1 #4)
const LIMIT_USER = 10, LIMIT_ANON = 5;

export async function POST(req: Request) {
  // 1) 입력 검증
  if (!isSameSiteJson(req)) return fail(415, "BAD_REQUEST", "잘못된 요청이에요.");
  const parsed = parseSurvey(await readJson(req));
  if (!parsed.ok) return fail(400, parsed.error, "설문 답변을 다시 확인해 주세요.");
  const survey = parsed.value;

  try {
    const userId = await getUserId();
    const wait = rateLimit(clientKey(req, "recommend", userId), userId ? LIMIT_USER : LIMIT_ANON, 60_000);
    if (wait) return fail(429, "RATE_LIMITED", `잠시 후(${wait}초) 다시 시도해 주세요.`, { "Retry-After": String(wait) });

    // 2) 상품 조회 — products는 공개 읽기라 publishable 키(RLS 적용)로 충분하다(최소 권한)
    const session = await createSessionClient();
    const { data, error } = await session
      .from("products")
      .select("id,name,category,tags,portion,price,stock")
      .gt("stock", 0);
    if (error) throw new Error(`products:${error.code}`);

    // 3) 룰 점수로 3개
    const ranked = rankProducts((data ?? []) as Product[], survey);

    // 4) 설문 저장 — 쓰기는 서버(secret 키)만
    const admin = createAdminClient();
    const { data: saved, error: insErr } = await admin
      .from("surveys")
      .insert({ ...survey, user_id: userId })
      .select("id")
      .single();
    if (insErr) throw new Error(`surveys:${insErr.code}`);

    // 5) AI 추천 사유 — 실패하면 기본 문구
    const reasons = await generateReasons(ranked.map((r) => r.product), survey);
    const items: Recommendation[] = ranked.map(({ product, score }) => {
      const ai = reasons?.get(product.id);
      return {
        product,
        score,
        reason: ai ?? fallbackReason(product, survey),
        reasonSource: ai ? "ai" : "fallback",
      };
    });

    return NextResponse.json({ ok: true, surveyId: saved.id, items });
  } catch (e) {
    console.error("[recommend]", e instanceof Error ? e.message : e);
    return fail(500, "SERVER_ERROR", "추천을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
  }
}
