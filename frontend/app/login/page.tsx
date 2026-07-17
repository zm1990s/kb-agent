"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import { setAuth } from "@/lib/auth";
import type { TokenResponse } from "@/lib/types";

interface RegisterResponse {
  id: string;
  email: string;
  role: string;
  created_at: string;
  email_verification_pending: boolean;
}

export default function LoginPage() {
  const router = useRouter();
  const t = useTranslations("login");
  const [mode, setMode] = useState<"login" | "register" | "forgot" | "reset" | "verify-pin">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [resetNewPassword, setResetNewPassword] = useState("");
  const [verifyPin, setVerifyPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      if (mode === "register") {
        const reg = await api.post<RegisterResponse>("/auth/register", { email, password });
        if (reg.email_verification_pending) {
          setMode("verify-pin");
          setBusy(false);
          return;
        }
      }
      const tok = await api.post<TokenResponse>("/auth/login", { email, password });
      setAuth(tok.access_token, tok.role, email);
      router.replace("/chat");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 423) {
          const d = err.detail as { remaining_seconds?: number } | null;
          const minutes = Math.ceil((d?.remaining_seconds ?? 900) / 60);
          setError(t("err_account_locked", { minutes }));
        } else if (err.status === 403 && err.message === "email_not_verified")
          setError(t("err_email_not_verified"));
        else if (err.status === 403) setError(t("err_domain"));
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

  async function onForgot(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setInfo(t("forgot_sent"));
      setMode("reset");
    } catch {
      setInfo(t("forgot_sent"));
      setMode("reset");
    } finally {
      setBusy(false);
    }
  }

  async function onReset(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      await api.post("/auth/reset-password", {
        email,
        code: resetCode,
        new_password: resetNewPassword,
      });
      setInfo(t("reset_success"));
      setResetCode("");
      setResetNewPassword("");
      setTimeout(() => {
        setMode("login");
        setInfo(null);
      }, 2000);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError(t("err_reset_invalid"));
      } else {
        setError(t("err_reset_invalid"));
      }
    } finally {
      setBusy(false);
    }
  }

  async function onVerifyPin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.post("/auth/verify-email-pin", { email, pin: verifyPin });
      // 验证成功，自动登录
      const tok = await api.post<TokenResponse>("/auth/login", { email, password });
      setAuth(tok.access_token, tok.role, email);
      router.replace("/chat");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError(t("err_pin_invalid"));
      } else {
        setError(t("err_pin_invalid"));
      }
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next: "login" | "register" | "forgot" | "reset" | "verify-pin") {
    setMode(next);
    setError(null);
    setInfo(null);
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
            {mode === "login"
              ? t("subtitle_login")
              : mode === "register"
              ? t("subtitle_register")
              : mode === "forgot"
              ? t("forgot_title")
              : mode === "verify-pin"
              ? t("verify_pin_title")
              : t("reset_title")}
          </p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">

          {/* ── 登录 / 注册表单 ── */}
          {(mode === "login" || mode === "register") && (
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
                <p className="text-center text-xs">
                  <button
                    type="button"
                    onClick={() => switchMode("forgot")}
                    className="text-blue-500 hover:underline"
                  >
                    {t("forgot_password_link")}
                  </button>
                </p>
              )}
            </form>
          )}

          {/* ── 邮箱 PIN 验证 ── */}
          {mode === "verify-pin" && (
            <form onSubmit={onVerifyPin} className="space-y-4">
              <p className="text-sm text-gray-500">{t("verify_pin_desc", { email })}</p>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">{t("verify_pin_label")}</label>
                <input
                  type="text"
                  required
                  maxLength={6}
                  minLength={6}
                  autoFocus
                  value={verifyPin}
                  onChange={(e) => setVerifyPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all tracking-widest text-center text-lg"
                  placeholder="000000"
                />
              </div>
              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}
              <button
                type="submit"
                disabled={busy || verifyPin.length !== 6}
                className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {busy ? t("processing") : t("verify_pin_submit")}
              </button>
            </form>
          )}

          {/* ── 忘记密码：输入邮箱 ── */}
          {mode === "forgot" && (
            <form onSubmit={onForgot} className="space-y-4">
              <p className="text-sm text-gray-500">{t("forgot_desc")}</p>
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

              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}
              {info && (
                <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
                  {info}
                </div>
              )}

              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {busy ? t("processing") : t("forgot_submit")}
              </button>
            </form>
          )}

          {/* ── 重置密码：输入验证码 + 新密码 ── */}
          {mode === "reset" && (
            <form onSubmit={onReset} className="space-y-4">
              {info && (
                <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
                  {info}
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">{t("reset_code_label")}</label>
                <input
                  type="text"
                  required
                  maxLength={6}
                  minLength={6}
                  value={resetCode}
                  onChange={(e) => setResetCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all tracking-widest"
                  placeholder="000000"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-gray-700">{t("reset_new_password")}</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={resetNewPassword}
                  onChange={(e) => setResetNewPassword(e.target.value)}
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
                {busy ? t("processing") : t("reset_submit")}
              </button>

              <p className="text-center text-xs">
                <button
                  type="button"
                  onClick={() => switchMode("forgot")}
                  className="text-blue-500 hover:underline"
                >
                  {t("forgot_submit")}
                </button>
              </p>
            </form>
          )}

          {/* ── 底部切换链接 ── */}
          <div className="mt-4 border-t border-gray-100 pt-4">
            {(mode === "login" || mode === "register") && (
              <button
                onClick={() => switchMode(mode === "login" ? "register" : "login")}
                className="w-full text-center text-sm text-blue-600 hover:text-blue-700 hover:underline transition-colors"
              >
                {mode === "login" ? t("switch_to_register") : t("switch_to_login")}
              </button>
            )}
            {(mode === "forgot" || mode === "reset" || mode === "verify-pin") && (
              <button
                onClick={() => switchMode("login")}
                className="w-full text-center text-sm text-blue-600 hover:text-blue-700 hover:underline transition-colors"
              >
                {t("switch_to_login")}
              </button>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
