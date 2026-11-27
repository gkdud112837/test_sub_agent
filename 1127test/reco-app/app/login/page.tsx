"use client";
// 이메일 매직링크 로그인 — 브라우저에서 publishable 키로 Supabase Auth 호출(비밀 키 불필요)
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/browser";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [linkFailed, setLinkFailed] = useState(false);

  // /auth/callback 실패 시 ?error=1 로 돌아온다 (review_v1 #11)
  useEffect(() => {
    setLinkFailed(new URLSearchParams(window.location.search).get("error") === "1");
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) || value.length > 254) { setState("error"); return; }
    setState("sending");
    try {
      const { error } = await createClient().auth.signInWithOtp({
        email: value,
        options: { emailRedirectTo: `${window.location.origin}/auth/callback?next=/me` },
      });
      setState(error ? "error" : "sent");
    } catch {
      setState("error");
    }
  }

  return (
    <section>
      <h1>로그인</h1>
      <p className="muted">이메일로 받은 링크를 누르면 로그인돼요. 로그인하면 내 주문만 따로 볼 수 있어요.</p>
      {linkFailed && state === "idle" && (
        <p className="msg err">로그인 링크가 만료됐거나 다른 브라우저에서 열렸어요. 이 브라우저에서 링크를 다시 받아 주세요.</p>
      )}
      <form onSubmit={submit} style={{ maxWidth: 360 }}>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
        <p><button type="submit" disabled={state === "sending"}>{state === "sending" ? "보내는 중…" : "로그인 링크 받기"}</button></p>
      </form>
      {state === "sent" && <p className="msg">메일함을 확인해 주세요.</p>}
      {state === "error" && <p className="msg err">링크를 보내지 못했어요. 이메일 주소를 확인하고 잠시 후 다시 시도해 주세요.</p>}
    </section>
  );
}
