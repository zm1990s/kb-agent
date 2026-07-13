"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearAuth, getEmail, isAdmin } from "@/lib/auth";

// 每个导航项对应一个 RBAC 模块；level != none 才显示。
const links = [
  { href: "/whatsnew", label: "新动态", module: "whatsnew" },
  { href: "/chat", label: "聊天", module: "chat" },
  { href: "/documents", label: "文档管理", module: "documents" },
  { href: "/stats", label: "数据统计", module: "stats" },
  { href: "/settings", label: "系统设置", module: "settings" },
];

interface Branding {
  name: string;
  logo_url: string;
}

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const admin = isAdmin();
  const email = getEmail();
  const [perms, setPerms] = useState<Record<string, string> | null>(null);
  const [branding, setBranding] = useState<Branding>({ name: "KB-Agent", logo_url: "" });
  const [dropOpen, setDropOpen] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .get<Record<string, string>>("/auth/my-permissions")
      .then(setPerms)
      .catch(() => setPerms({}));
    api
      .get<Branding>("/settings/branding")
      .then(setBranding)
      .catch(() => {});
  }, []);

  // 点击外部关闭 dropdown
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setDropOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  const visible = links.filter((l) => {
    if (admin) return true;
    if (l.module === "chat") return true;
    if (!perms) return false;
    // /settings 合并了空间管理和用户管理，三个模块任一有权限即可见
    if (l.href === "/settings") {
      return ["settings", "workspaces", "users"].some(
        (m) => (perms[m] ?? "none") !== "none"
      );
    }
    return (perms[l.module] ?? "none") !== "none";
  });

  return (
    <>
      <nav className="relative flex items-center bg-gray-900 px-4 py-2">
        {/* 左：Logo + 平台名（点击回首页） */}
        <div className="flex w-48 shrink-0 items-center">
          <Link href="/chat" className="flex items-center gap-2 text-white/90 hover:text-white">
            {branding.logo_url ? (
              <Image
                src={branding.logo_url}
                alt="logo"
                width={28}
                height={28}
                className="h-7 w-7 rounded object-contain"
                unoptimized
              />
            ) : (
              <span className="flex h-7 w-7 items-center justify-center rounded bg-blue-500 text-xs font-bold text-white">
                {branding.name.slice(0, 2)}
              </span>
            )}
            <span className="font-semibold tracking-wide">{branding.name}</span>
          </Link>
        </div>

        {/* 中：菜单居中 */}
        <div className="absolute left-1/2 flex -translate-x-1/2 items-center gap-0.5">
          {visible.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded px-3 py-1.5 text-sm transition-colors ${
                pathname === l.href
                  ? "bg-white/15 text-white font-medium"
                  : "text-gray-300 hover:bg-white/10 hover:text-white"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>

        {/* 右：用户 dropdown */}
        <div className="ml-auto flex items-center" ref={dropRef}>
          <button
            onClick={() => setDropOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded px-3 py-1.5 text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors"
          >
            <span className="max-w-[120px] truncate">{email ?? "用户"}</span>
            <svg className="h-3 w-3 opacity-60" viewBox="0 0 10 6" fill="currentColor">
              <path d="M0 0l5 6 5-6z" />
            </svg>
          </button>
          {dropOpen && (
            <div className="absolute right-4 top-full z-50 mt-1 w-40 rounded border border-gray-700 bg-gray-800 py-1 shadow-xl">
              <Link
                href="/account"
                onClick={() => setDropOpen(false)}
                className="block px-4 py-2 text-sm text-gray-200 hover:bg-white/10 hover:text-white"
              >
                账户管理
              </Link>
              <div className="my-1 border-t border-gray-700" />
              <button
                onClick={logout}
                className="block w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-white/10 hover:text-red-300"
              >
                退出登录
              </button>
            </div>
          )}
        </div>
      </nav>

    </>
  );
}
