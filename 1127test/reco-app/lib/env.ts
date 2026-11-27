// 환경변수 이름은 CLAUDE.md · .env.example과 같아야 한다. 값은 코드에 쓰지 않는다.
// NEXT_PUBLIC_ 이 붙은 두 개만 브라우저 코드에 들어간다(빌드 때 치환).
export const publicEnv = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabasePublishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
};

export function hasPublicEnv() {
  return Boolean(publicEnv.supabaseUrl && publicEnv.supabasePublishableKey);
}
