"use client";
// 브라우저용 클라이언트: publishable 키만 사용. RLS가 허락한 행만 읽을 수 있다.
import { createBrowserClient } from "@supabase/ssr";
import { publicEnv } from "@/lib/env";

export function createClient() {
  return createBrowserClient(publicEnv.supabaseUrl, publicEnv.supabasePublishableKey);
}
