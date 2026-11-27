// 입력 검증 — spec.md 보안 절 "입력": 정해진 선택지 값만, 자유 입력 200자 이하, 빈 값은 저장 안 함.
// 통과하지 못하면 이유 코드만 돌려준다(내부 정보 노출 없음).
import { BUDGETS, CATEGORIES, COOKINGS, HOUSEHOLDS, type SurveyInput } from "@/lib/types";

type Result<T> = { ok: true; value: T } | { ok: false; error: string };

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function parseSurvey(body: unknown): Result<SurveyInput> {
  if (!isObj(body)) return { ok: false, error: "BAD_BODY" };
  const { household, categories, budget, cooking, note } = body;

  if (!HOUSEHOLDS.includes(household as never)) return { ok: false, error: "BAD_HOUSEHOLD" };
  if (
    !Array.isArray(categories) ||
    categories.length < 1 ||
    categories.length > 3 ||
    !categories.every((c) => CATEGORIES.includes(c as never)) ||
    new Set(categories).size !== categories.length
  ) return { ok: false, error: "BAD_CATEGORIES" };
  if (!BUDGETS.includes(budget as never)) return { ok: false, error: "BAD_BUDGET" };
  if (!COOKINGS.includes(cooking as never)) return { ok: false, error: "BAD_COOKING" };

  let cleanNote: string | null = null;
  if (note !== undefined && note !== null) {
    if (typeof note !== "string") return { ok: false, error: "BAD_NOTE" };
    const t = note.trim();
    if (t.length > 200) return { ok: false, error: "NOTE_TOO_LONG" };
    cleanNote = t.length ? t : null;
  }

  return {
    ok: true,
    value: {
      household: household as SurveyInput["household"],
      categories: categories as SurveyInput["categories"],
      budget: budget as number,
      cooking: cooking as SurveyInput["cooking"],
      note: cleanNote,
    },
  };
}

export type OrderInput = { productId: number; qty: number; surveyId: number | null };

const isPosInt = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) > 0;

export function parseOrder(body: unknown): Result<OrderInput> {
  if (!isObj(body)) return { ok: false, error: "BAD_BODY" };
  const { productId, qty, surveyId } = body;
  if (!isPosInt(productId)) return { ok: false, error: "BAD_PRODUCT" };
  if (!isPosInt(qty) || qty > 20) return { ok: false, error: "BAD_QTY" };
  if (surveyId !== undefined && surveyId !== null && !isPosInt(surveyId)) return { ok: false, error: "BAD_SURVEY" };
  return { ok: true, value: { productId, qty, surveyId: (surveyId as number | null | undefined) ?? null } };
}
