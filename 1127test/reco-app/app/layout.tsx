import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "대구 오늘의 식재료 추천",
  description: "설문 3문항으로 고르는 오늘의 식재료 (실습용 가상 데이터)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="top">
          <Link href="/" className="brand">대구 오늘의 식재료</Link>
          <nav>
            <Link href="/me">내 주문</Link>
            <Link href="/login">로그인</Link>
          </nav>
        </header>
        <main>{children}</main>
        <footer>실습용 가상 데이터 · 상품명·가격·재고는 설명용입니다.</footer>
      </body>
    </html>
  );
}
