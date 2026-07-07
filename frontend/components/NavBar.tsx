"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearAuth, isAdmin } from "@/lib/auth";

const links = [
  { href: "/chat", label: "对话查询", adminOnly: false },
  { href: "/documents", label: "文档管理", adminOnly: false },
  { href: "/admin", label: "空间管理", adminOnly: true },
];

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const admin = isAdmin();

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  return (
    <nav className="flex items-center gap-1 border-b bg-white px-4 py-2">
      <span className="mr-4 font-semibold">KB-Agent</span>
      {links
        .filter((l) => !l.adminOnly || admin)
        .map((l) => (
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
