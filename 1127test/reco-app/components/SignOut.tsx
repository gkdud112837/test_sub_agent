"use client";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/browser";

export default function SignOut() {
  const router = useRouter();
  return (
    <button type="button" className="ghost" onClick={async () => { await createClient().auth.signOut(); router.refresh(); }}>
      로그아웃
    </button>
  );
}
