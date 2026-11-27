import "server-only";
// secret 키 클라이언트: RLS를 건너뛰는 전체 권한. app/api/ 서버 함수에서만 import 한다.
// "server-only" 때문에 클라이언트 컴포넌트에서 import 하면 빌드가 실패한다(키 노출 방지 장치).
import { createClient } from "@supabase/supabase-js";
import { publicEnv } from "@/lib/env";

export function createAdminClient() {
  const secret = process.env.SUPABASE_SECRET_KEY;
  if (!publicEnv.supabaseUrl || !secret) {
    throw new Error("MISSING_ENV: NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SECRET_KEY");
  }
  return createClient(publicEnv.supabaseUrl, secret, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
