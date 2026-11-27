import "server-only";
// 서버용 "사용자 세션" 클라이언트: publishable 키 + 쿠키의 로그인 세션 → RLS가 그대로 적용된다.
// (로그인 사용자 확인, 본인 행 조회에 사용. 쓰기에는 쓰지 않는다)
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { publicEnv } from "@/lib/env";

export async function createSessionClient() {
  const cookieStore = await cookies();
  return createServerClient(publicEnv.supabaseUrl, publicEnv.supabasePublishableKey, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (list) => {
        try {
          list.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // 서버 컴포넌트에서는 쿠키를 쓸 수 없다 — 라우트 핸들러에서 갱신된다
        }
      },
    },
  });
}

/** 로그인한 사용자의 id. 비로그인·세션 만료·환경변수 없음이면 null */
export async function getUserId(): Promise<string | null> {
  try {
    const supabase = await createSessionClient();
    const { data } = await supabase.auth.getUser(); // getSession이 아니라 getUser: 서버에서 토큰을 검증
    return data.user?.id ?? null;
  } catch {
    return null;
  }
}
