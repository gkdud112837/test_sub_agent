// 세션 갱신 (review_v1 #5) — Next.js 16의 proxy(구 middleware).
// 서버 컴포넌트는 쿠키를 쓸 수 없으므로, 요청마다 여기서 getUser()로 토큰을 검증·갱신하고 새 쿠키를 응답에 실는다.
import { NextResponse, type NextRequest } from "next/server";
import { createServerClient } from "@supabase/ssr";

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) return response;

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (list) => {
        list.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        list.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });
  await supabase.auth.getUser();
  return response;
}

export const config = {
  // 정적 파일·이미지·API는 건너뛴다 (review_v1 N2 — API 라우트는 스스로 쿠키를 갱신할 수 있어 Auth 호출이 두 번 될 필요 없음)
  matcher: ["/((?!api/|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
