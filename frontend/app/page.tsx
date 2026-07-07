"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn } from "@/lib/auth";

// 首页：按登录态重定向到对话页或登录页。
export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(isLoggedIn() ? "/chat" : "/login");
  }, [router]);
  return null;
}
