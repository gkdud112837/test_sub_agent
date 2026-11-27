// review_v1 #1 회귀 테스트: node scripts/test_redirect.ts
import { safeRedirectPath } from "../lib/redirect.ts";

const origin = "https://reco.example";
const cases: [string | null, string][] = [
  ["/%09/evil.example", "/me"].map((v, i) => (i === 0 ? decodeURIComponent(v as string) : v)) as [string, string],
  ["/\n/evil.example", "/me"],
  ["//evil.example", "/me"],
  ["/" + String.fromCharCode(92) + "evil.example", "/me"],
  ["https://evil.example/me", "/me"],
  ["javascript:alert(1)", "/me"],
  [null, "/me"],
  ["/me", "/me"],
  ["/me?tab=orders", "/me?tab=orders"],
];
let fail = 0;
for (const [input, want] of cases) {
  const got = safeRedirectPath(input, origin);
  const ok = got === want;
  if (!ok) fail++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${JSON.stringify(input)} → ${got}`);
}
process.exit(fail ? 1 : 0);
