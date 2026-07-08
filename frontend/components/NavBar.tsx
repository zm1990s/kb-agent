"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearAuth, isAdmin } from "@/lib/auth";

// 每个导航项对应一个 RBAC 模块；level != none 才显示。
const links = [
  { href: "/chat", label: "对话查询", module: "chat" },
  { href: "/documents", label: "文档管理", module: "documents" },
  { href: "/admin", label: "空间管理", module: "workspaces" },
  { href: "/users", label: "用户管理", module: "users" },
  { href: "/settings", label: "系统设置", module: "settings" },
];

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const admin = isAdmin();
  const [perms, setPerms] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    api
      .get<Record<string, string>>("/auth/my-permissions")
      .then(setPerms)
      .catch(() => setPerms({}));
  }, []);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  // admin 看全部；对话查询对所有登录用户开放（核心功能）；
  // 其余模块按 RBAC 权限（level != none 才显示）。
  const visible = links.filter((l) => {
    if (admin) return true;
    if (l.module === "chat") return true;
    if (!perms) return false;
    return (perms[l.module] ?? "none") !== "none";
  });

  return (
    <nav className="flex items-center gap-1 border-b bg-white px-4 py-2">
      <span className="mr-4 font-semibold">KB-Agent</span>
      {visible.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`rounded px-3 py-1.5 text-sm ${
            pathname === l.href
              ? "bg-blue-50 text-blue-700"
              : "text-gray-600 hover:bg-gray-100"
          }`}
        >
          {l.label}
        </Link>
      ))}
      <button
        onClick={logout}
        className="ml-auto rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
      >
        退出
      </button>
    </nav>
  );
}
