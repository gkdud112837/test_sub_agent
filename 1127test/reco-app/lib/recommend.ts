// 룰 점수 — 같은 상품 목록이라도 설문 답변에 따라 순서가 달라진다(개인화).
// 재고 0 · 예산 초과 상품은 후보에서 뺀다.
import type { Product, SurveyInput } from "@/lib/types";

export function scoreProduct(p: Product, s: SurveyInput): number {
  let score = 0;
  if (s.categories.includes(p.category)) score += 3;  // 선호 분류
  if (p.portion === s.household) score += 2;           // 가구 수 = 포장 단위
  if (p.tags.includes(s.cooking)) score += 1;          // 간편 / 요리
  if (p.price <= s.budget / 2) score += 0.5;           // 예산 여유
  return score;
}

export function rankProducts(products: Product[], s: SurveyInput, limit = 3) {
  return products
    .filter((p) => p.stock > 0 && p.price <= s.budget)
    .map((p) => ({ product: p, score: scoreProduct(p, s) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.product.price - b.product.price || a.product.id - b.product.id)
    .slice(0, limit);
}

/** AI 실패 시 기본 문구 — DB에 있는 값만으로 만든다 */
export function fallbackReason(p: Product, s: SurveyInput): string {
  const parts: string[] = [];
  if (s.categories.includes(p.category)) parts.push(`선호하신 ${p.category}`);
  if (p.portion === s.household) parts.push(`${p.portion} 포장`);
  if (p.tags.includes(s.cooking)) parts.push(`${s.cooking} 조리`);
  return parts.length ? `${parts.join(" · ")} 조건에 맞는 상품입니다.` : "설문 조건에 가까운 상품입니다.";
}
