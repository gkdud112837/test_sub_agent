/** 오픈 리다이렉트 방지: 문자열 검사 대신 실제로 URL을 해석해 우리 사이트(origin)인지 비교한다.
 *  (review_v1 #1 — "/%09/evil.example"은 접두사 검사를 통과하지만 URL 해석 시 //evil.example 이 됨) */
export function safeRedirectPath(next: string | null, origin: string): string {
  if (!next) return "/me";
  try {
    const target = new URL(next, origin);
    if (target.origin !== origin) return "/me";
    return target.pathname + target.search;
  } catch {
    return "/me";
  }
}
