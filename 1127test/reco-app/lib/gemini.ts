import "server-only";
// Gemini 추천 사유 — 서버에서만 호출(GEMINI_API_KEY는 브라우저에 가지 않는다).
// 흐름: 프롬프트 조립(DB 값 + 설문 선택지만) → JSON 구조화 출력 요청 → 서버에서 형식 검사 → 실패하면 null.
// 호출한 쪽은 null을 받으면 기본 문구를 쓴다.
import type { Product, SurveyInput } from "@/lib/types";

const ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models";
const TIMEOUT_MS = 8000;
const MAX_REASON = 60; // 프롬프트는 40자 이내를 요구, 서버는 여유를 두고 60자에서 자른다
// 지어낸 수치 차단 (review_v1 #6): 모든 유니코드 숫자(전각 포함) + 수치 단위·한글 수사
const HAS_NUMBER = /[\p{Nd}%]|[0-9０-９]|(?<![a-z])(?:kg|g|mg|kcal)(?![a-z])|(?:칼로리|그램|퍼센트|배\s*이상|절반)|(?:^|\s)(?:한|두|세|네|다섯|열|백|천|만)\s*(?:개|배|번|가지|그램|근|팩|봉)/iu;

function buildPrompt(products: Product[], s: SurveyInput): string {
  // 자유 입력(note)은 넣지 않는다 — 지시를 바꾸려는 문장(프롬프트 주입) 차단
  const survey = `가구: ${s.household}, 선호 분류: ${s.categories.join("·")}, 조리: ${s.cooking}, 1개당 예산: ${s.budget}원 이하`;
  const items = products
    .map((p) => `- id ${p.id}: ${p.name} / 분류 ${p.category} / 속성 ${p.tags.join("·")} / 포장 ${p.portion}`)
    .join("\n");
  return [
    "너는 대구 오늘의 식재료 추천 서비스의 도우미다.",
    `사용자 설문: ${survey}`,
    "추천 상품:",
    items,
    "각 상품을 추천한 이유를 한국어 한 문장(40자 이내)으로 써라.",
    "위 상품 정보와 설문에 없는 효능·원산지·수치·가격은 쓰지 말 것.",
    '형식: [{"id": 상품 id, "reason": "..."}] JSON 배열로만 답한다.',
  ].join("\n");
}

const RESPONSE_SCHEMA = {
  type: "ARRAY",
  items: {
    type: "OBJECT",
    properties: { id: { type: "INTEGER" }, reason: { type: "STRING" } },
    required: ["id", "reason"],
  },
};

/** 상품 id → 사유. 키 없음 · 한도 초과 · 시간 초과 · 형식 오류면 null */
export async function generateReasons(products: Product[], s: SurveyInput): Promise<Map<number, string> | null> {
  const key = process.env.GEMINI_API_KEY;
  if (!key || products.length === 0) return null;
  const model = process.env.GEMINI_MODEL || "gemini-flash-latest";

  try {
    const res = await fetch(`${ENDPOINT}/${encodeURIComponent(model)}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": key }, // 키는 URL이 아니라 헤더로
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: buildPrompt(products, s) }] }],
        generationConfig: {
          responseMimeType: "application/json",
          responseSchema: RESPONSE_SCHEMA,
          temperature: 0.4,
          maxOutputTokens: 512,
        },
      }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    if (!res.ok) {
      console.warn("[gemini] HTTP", res.status); // 429 = 한도 초과 → 기본 문구
      return null;
    }
    const data = await res.json();
    const text: unknown = data?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (typeof text !== "string") return null;
    return validateReasons(JSON.parse(text), products);
  } catch (e) {
    console.warn("[gemini] failed:", e instanceof Error ? e.name : "unknown");
    return null;
  }
}

/** 서버 형식 검사: 배열 · 후보 id만 · 문자열 · 길이 · 숫자 금지(지어낸 수치 차단) */
export function validateReasons(raw: unknown, products: Product[]): Map<number, string> | null {
  if (!Array.isArray(raw)) return null;
  const allowed = new Set(products.map((p) => p.id));
  const out = new Map<number, string>();
  for (const item of raw) {
    if (typeof item !== "object" || item === null) continue;
    const { id, reason } = item as { id?: unknown; reason?: unknown };
    if (typeof id !== "number" || !allowed.has(id) || typeof reason !== "string") continue;
    const r = reason.trim().replace(/\s+/g, " ");
    if (!r || r.length > MAX_REASON || HAS_NUMBER.test(r)) continue;
    out.set(id, r);
  }
  return out.size ? out : null;
}
