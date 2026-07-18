"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isLoggedIn, resolveLandingPath } from "@/lib/auth";

// 首页：按登录态 + 权限重定向到可访问页或登录页。
export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    resolveLandingPath().then((path) => router.replace(path));
  }, [router]);
  return null;
}
