import "server-only";
// 간단한 고정 창 레이트 리밋 (review_v1 #3·#4)
// ⚠ 메모리 저장이라 서버 인스턴스마다 따로 센다. Vercel에서는 인스턴스가 여러 개일 수 있어 "최선 노력" 수준이다.
//   운영 전환 시 Upstash Redis · Vercel KV 같은 공유 저장소로 바꾼다 (progress에 남은 항목).
const buckets = new Map<string, { count: number; resetAt: number }>();

export function clientKey(req: Request, scope: string, userId: string | null): string {
  if (userId) return `${scope}:u:${userId}`;
  // review_v1 N1: 클라이언트가 바꿀 수 있는 x-forwarded-for 첫 값 대신 플랫폼이 넣는 헤더를 우선한다
  //   Vercel = x-vercel-forwarded-for · x-real-ip (Vercel이 덮어씀). 둘 다 없을 때만 XFF의 마지막(프록시가 붙인) 값
  const xff = req.headers.get("x-forwarded-for")?.split(",").map((s) => s.trim()).filter(Boolean);
  const ip = req.headers.get("x-vercel-forwarded-for") || req.headers.get("x-real-ip") || xff?.at(-1) || "unknown";
  return `${scope}:ip:${ip}`;
}

/** 허용이면 0, 막히면 다시 시도까지 남은 초 */
export function rateLimit(key: string, limit: number, windowMs: number): number {
  const now = Date.now();
  if (buckets.size > 5000) for (const [k, b] of buckets) if (b.resetAt <= now) buckets.delete(k);
  const b = buckets.get(key);
  if (!b || b.resetAt <= now) {
    buckets.set(key, { count: 1, resetAt: now + windowMs });
    return 0;
  }
  if (b.count >= limit) return Math.ceil((b.resetAt - now) / 1000);
  b.count++;
  return 0;
}
