import { NextResponse } from "next/server";

/** 사용자에게 보이는 오류는 짧은 한국어 문장 + 코드만. DB 오류 원문·스택은 보내지 않는다. */
export function fail(status: number, code: string, message: string, headers?: HeadersInit) {
  return NextResponse.json({ ok: false, code, message }, { status, headers });
}

/** 같은 사이트에서 온 JSON 요청인지 (review_v1 #8 — text/plain 교차 사이트 POST 차단) */
export function isSameSiteJson(req: Request): boolean {
  const ct = req.headers.get("content-type") ?? "";
  if (!ct.toLowerCase().startsWith("application/json")) return false;
  const origin = req.headers.get("origin");
  if (!origin) return true; // 서버 간 호출·curl 등 Origin 없는 요청은 Content-Type 검사로 충분
  try {
    return new URL(origin).host === new URL(req.url).host;
  } catch {
    return false;
  }
}

/** 본문을 읽으며 바이트 상한을 넘으면 중단한다 (review_v1 #7 — 글자 수가 아니라 바이트) */
export async function readJson(req: Request, maxBytes = 4096): Promise<unknown> {
  if (Number(req.headers.get("content-length") ?? 0) > maxBytes) return undefined;
  if (!req.body) return undefined;
  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBytes) { await reader.cancel(); return undefined; }
    chunks.push(value);
  }
  const buf = new Uint8Array(size);
  let off = 0;
  for (const c of chunks) { buf.set(c, off); off += c.byteLength; }
  try { return JSON.parse(new TextDecoder().decode(buf)); } catch { return undefined; }
}
