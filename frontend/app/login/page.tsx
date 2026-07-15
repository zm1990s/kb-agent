"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { setAuth } from "@/lib/auth";
import type { TokenResponse, UserPublic } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const t = useTranslations("login");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await api.post<UserPublic>("/auth/register", { email, password });
      }
      const tok = await api.post<TokenResponse>("/auth/login", { email, password });
      setAuth(tok.access_token, tok.role, email);
      router.replace("/chat");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) setError(t("err_domain"));
        else if (err.status === 409) setError(t("err_duplicate"));
        else if (err.status === 401) setError(t("err_credentials"));
        else setError(err.message);
      } else {
        setError(t("err_credentials"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
      <div className="w-full max-w-sm">
        {/* Logo / brand */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 text-white">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-900">{t("title")}</h1>
          <p className="mt-1 text-sm text-gray-500">
            {mode === "login" ? t("subtitle_login") : t("subtitle_register")}
          </p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">{t("email")}</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">{t("password")}</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
                placeholder={t("password_placeholder")}
              />
            </div>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {busy ? t("processing") : mode === "login" ? t("submit_login") : t("submit_register")}
            </button>

            {mode === "login" && (
              <p className="text-center text-xs text-gray-400">
                {t("forgot_password", { team: t("team_name") })}
              </p>
            )}
          </form>

          <div className="mt-4 border-t border-gray-100 pt-4">
            <button
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
              className="w-full text-center text-sm text-blue-600 hover:text-blue-700 hover:underline transition-colors"
            >
              {mode === "login" ? t("switch_to_register") : t("switch_to_login")}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
