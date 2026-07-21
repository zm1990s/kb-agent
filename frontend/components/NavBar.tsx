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

interface Subscription {
  email: string;
  frequency: string;
  last_sent_at: string | null;
}

const FREQ_VALUES = ["weekly", "biweekly", "monthly"] as const;

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
  const tWn = useTranslations("whatsnew");
  const [perms, setPerms] = useState<Record<string, string> | null>(null);
  const [branding, setBranding] = useState<Branding>({ name: "KB-Agent", logo_url: "" });
  const [dropOpen, setDropOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [subOpen, setSubOpen] = useState(false);
  const [sub, setSub] = useState<Subscription | null | "loading">("loading");
  const [subFreq, setSubFreq] = useState("weekly");
  const [subSaving, setSubSaving] = useState(false);
  const [subMsg, setSubMsg] = useState("");
  const dropRef = useRef<HTMLDivElement>(null);
  const langRef = useRef<HTMLDivElement>(null);
  const subRef = useRef<HTMLDivElement>(null);

  const links = [
    { href: "/whatsnew", label: t("whatsnew"), module: "whatsnew" },
    { href: "/chat", label: t("chat"), module: "chat" },
    { href: "/chat-plus", label: t("chatPlus"), module: "chatplus" },
    { href: "/skills", label: t("skills"), module: "skills" },
    { href: "/documents", label: t("documents"), module: "documents" },
    { href: "/case-entry", label: t("caseEntry"), module: "cases" },
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
    if (!subOpen || sub !== "loading") return;
    api.get<Subscription>("/whatsnew/subscription")
      .then((data) => { setSub(data); setSubFreq(data.frequency); })
      .catch(() => setSub(null));
  }, [subOpen]);

  // 路由跳转后关闭所有弹出层
  useEffect(() => {
    setMenuOpen(false);
    setDropOpen(false);
    setLangOpen(false);
    setSubOpen(false);
  }, [pathname]);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setDropOpen(false);
      }
      if (langRef.current && !langRef.current.contains(e.target as Node)) {
        setLangOpen(false);
      }
      if (subRef.current && !subRef.current.contains(e.target as Node)) {
        setSubOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  async function handleSubSave() {
    setSubSaving(true);
    setSubMsg("");
    try {
      const data = await api.put<Subscription>("/whatsnew/subscription", { frequency: subFreq });
      setSub(data);
      setSubMsg(tWn("sub_saved"));
    } catch {
      setSubMsg(tWn("sub_save_failed"));
    } finally {
      setSubSaving(false);
    }
  }

  async function handleSubDelete() {
    setSubSaving(true);
    setSubMsg("");
    try {
      await api.del("/whatsnew/subscription");
      setSub(null);
      setSubFreq("weekly");
      setSubMsg(tWn("sub_deleted"));
    } catch {
      setSubMsg(tWn("sub_delete_failed"));
    } finally {
      setSubSaving(false);
    }
  }

  const FREQ_OPTIONS = FREQ_VALUES.map((v) => ({
    value: v,
    label: tWn(`freq_${v}` as Parameters<typeof tWn>[0]),
  }));

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  const visible = links.filter((l) => {
    if (admin) return true;
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
          <Link href="/" className="flex items-center gap-2 text-white/90 hover:text-white">
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

        {/* 中：菜单居中（桌面） */}
        <div className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-0.5 md:flex">
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

        {/* 右：订阅 + 语言切换 + 用户 dropdown（桌面） */}
        <div className="ml-auto hidden items-center gap-1 md:flex">
          {/* 订阅铃铛 */}
          {perms && (perms["whatsnew"] ?? "none") !== "none" && (
            <div className="relative" ref={subRef}>
              <button
                onClick={() => { setSubOpen((v) => !v); setSubMsg(""); }}
                className="flex items-center justify-center rounded px-2 py-1.5 text-gray-400 hover:bg-white/10 hover:text-white transition-colors"
                title={tWn("subscription")}
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
                {sub && sub !== "loading" && (
                  <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-blue-400" />
                )}
              </button>
              {subOpen && (
                <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-gray-700 bg-gray-800 shadow-xl">
                  <div className="border-b border-gray-700 px-4 py-2.5">
                    <p className="text-sm font-medium text-white">{tWn("subscription")}</p>
                  </div>
                  <div className="p-4 space-y-3">
                    {/* 收件邮箱 */}
                    <div>
                      <p className="mb-1 text-xs text-gray-400">{tWn("sub_email")}</p>
                      <p className="truncate text-sm text-gray-200">{email ?? "—"}</p>
                    </div>
                    {/* 频率 */}
                    <div>
                      <p className="mb-1 text-xs text-gray-400">{tWn("sub_frequency")}</p>
                      <select
                        value={subFreq}
                        onChange={(e) => setSubFreq(e.target.value)}
                        className="w-full rounded border border-gray-600 bg-gray-700 px-2 py-1.5 text-sm text-gray-200 focus:border-blue-400 focus:outline-none"
                      >
                        {FREQ_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </div>
                    {/* 状态信息 */}
                    {sub && sub !== "loading" && (
                      <p className="text-xs text-gray-500">
                        {tWn("sub_current", { freq: FREQ_OPTIONS.find((o) => o.value === sub.frequency)?.label ?? sub.frequency })}
                        {sub.last_sent_at
                          ? tWn("sub_last_sent", { date: sub.last_sent_at.slice(0, 10) })
                          : tWn("sub_never_sent")}
                      </p>
                    )}
                    {/* 按钮 */}
                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={handleSubSave}
                        disabled={subSaving}
                        className="flex-1 rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                      >
                        {subSaving ? tWn("sub_save") : sub && sub !== "loading" ? tWn("sub_update") : tWn("sub_subscribe")}
                      </button>
                      {sub && sub !== "loading" && (
                        <button
                          onClick={handleSubDelete}
                          disabled={subSaving}
                          className="rounded border border-red-700 px-3 py-1.5 text-sm text-red-400 hover:bg-red-900/30 disabled:opacity-50 transition-colors"
                        >
                          {tWn("sub_unsubscribe")}
                        </button>
                      )}
                    </div>
                    {subMsg && (
                      <p className={`text-xs ${subMsg.includes("失败") || subMsg.toLowerCase().includes("fail") ? "text-red-400" : "text-green-400"}`}>
                        {subMsg}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

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

        {/* 汉堡按钮（移动端） */}
        <button
          className="ml-auto rounded p-2 text-gray-300 hover:bg-white/10 md:hidden"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="菜单"
        >
          {menuOpen ? (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </nav>

      {/* 移动端下拉面板 */}
      {menuOpen && (
        <div className="border-t border-gray-700 bg-gray-900 px-4 py-3 md:hidden">
          <div className="space-y-1">
            {visible.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`block rounded px-3 py-2 text-sm transition-colors ${
                  pathname === l.href
                    ? "bg-white/15 text-white font-medium"
                    : "text-gray-300 hover:bg-white/10 hover:text-white"
                }`}
              >
                {l.label}
              </Link>
            ))}
          </div>

          <div className="mt-2 space-y-1 border-t border-gray-700 pt-2">
            <p className="px-3 py-1 text-xs text-gray-500">{t("lang_label")}</p>
            {LOCALES.map((l) => (
              <button
                key={l}
                onClick={() => { setLocale(l); setMenuOpen(false); }}
                className={`block w-full rounded px-3 py-2 text-left text-sm hover:bg-white/10 ${
                  l === locale ? "text-white font-medium" : "text-gray-300"
                }`}
              >
                {LANG_LABELS[l]}
              </button>
            ))}
          </div>

          <div className="mt-2 space-y-1 border-t border-gray-700 pt-2">
            <p className="truncate px-3 py-1 text-xs text-gray-500">{email ?? t("user_fallback")}</p>
            <Link
              href="/account"
              onClick={() => setMenuOpen(false)}
              className="block rounded px-3 py-2 text-sm text-gray-200 hover:bg-white/10 hover:text-white"
            >
              {t("account")}
            </Link>
            <button
              onClick={() => { logout(); setMenuOpen(false); }}
              className="block w-full rounded px-3 py-2 text-left text-sm text-red-400 hover:bg-white/10 hover:text-red-300"
            >
              {t("logout")}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
