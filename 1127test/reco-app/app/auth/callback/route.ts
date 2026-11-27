// 매직링크가 돌아오는 곳: code → 세션 쿠키 교환 후 이동
import { NextResponse } from "next/server";
import { createSessionClient } from "@/lib/supabase/server";
import { safeRedirectPath } from "@/lib/redirect";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const next = safeRedirectPath(url.searchParams.get("next"), url.origin);

  if (code) {
    const supabase = await createSessionClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(new URL(next, url.origin));
  }
  return NextResponse.redirect(new URL("/login?error=1", url.origin));
}
