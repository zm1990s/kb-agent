"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { clearAuth, getEmail, isAdmin } from "@/lib/auth";
import { useLocale } from "@/components/IntlProvider";
import { LOCALES, type Locale } from "@/lib/locale";

const LANG_LABELS: Record<Locale, string> = {
  zh: "简体中文",
  "zh-TW": "繁體中文",
  en: "English",
  ja: "日本語",
  ko: "한국어",
};

interface Branding {
  name: string;
  logo_url: string;
}

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("nav");
  const { locale, setLocale } = useLocale();
  const admin = isAdmin();
  const email = getEmail();
  const [perms, setPerms] = useState<Record<string, string> | null>(null);
  const [branding, setBranding] = useState<Branding>({ name: "KB-Agent", logo_url: "" });
  const [dropOpen, setDropOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);
  const langRef = useRef<HTMLDivElement>(null);

  const links = [
    { href: "/whatsnew", label: t("whatsnew"), module: "whatsnew" },
    { href: "/chat", label: t("chat"), module: "chat" },
    { href: "/documents", label: t("documents"), module: "documents" },
    { href: "/stats", label: t("stats"), module: "stats" },
    { href: "/settings", label: t("settings"), module: "settings" },
  ];

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

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setDropOpen(false);
      }
      if (langRef.current && !langRef.current.contains(e.target as Node)) {
        setLangOpen(false);
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
        {/* 左：Logo + 平台名 */}
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

        {/* 右：语言切换 + 用户 dropdown */}
        <div className="ml-auto flex items-center gap-1">
          {/* 语言切换 */}
          <div className="relative" ref={langRef}>
            <button
              onClick={() => setLangOpen((v) => !v)}
              className="flex items-center gap-1 rounded px-2 py-1.5 text-xs text-gray-400 hover:bg-white/10 hover:text-white transition-colors"
              title={t("lang_label")}
            >
              <span>{LANG_LABELS[locale]}</span>
              <svg className="h-3 w-3 opacity-60" viewBox="0 0 10 6" fill="currentColor">
                <path d="M0 0l5 6 5-6z" />
              </svg>
            </button>
            {langOpen && (
              <div className="absolute right-0 top-full z-50 mt-1 w-32 rounded border border-gray-700 bg-gray-800 py-1 shadow-xl">
                {LOCALES.map((l) => (
                  <button
                    key={l}
                    onClick={() => { setLocale(l); setLangOpen(false); }}
                    className={`block w-full px-4 py-2 text-left text-sm hover:bg-white/10 ${
                      l === locale ? "text-white font-medium" : "text-gray-300"
                    }`}
                  >
                    {LANG_LABELS[l]}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 用户 dropdown */}
          <div className="relative" ref={dropRef}>
            <button
              onClick={() => setDropOpen((v) => !v)}
              className="flex items-center gap-1.5 rounded px-3 py-1.5 text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors"
            >
              <span className="max-w-[120px] truncate">{email ?? t("user_fallback")}</span>
              <svg className="h-3 w-3 opacity-60" viewBox="0 0 10 6" fill="currentColor">
                <path d="M0 0l5 6 5-6z" />
              </svg>
            </button>
            {dropOpen && (
              <div className="absolute right-0 top-full z-50 mt-1 w-40 rounded border border-gray-700 bg-gray-800 py-1 shadow-xl">
                <Link
                  href="/account"
                  onClick={() => setDropOpen(false)}
                  className="block px-4 py-2 text-sm text-gray-200 hover:bg-white/10 hover:text-white"
                >
                  {t("account")}
                </Link>
                <div className="my-1 border-t border-gray-700" />
                <button
                  onClick={logout}
                  className="block w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-white/10 hover:text-red-300"
                >
                  {t("logout")}
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>
    </>
  );
}
