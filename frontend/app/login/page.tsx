"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { setAuth } from "@/lib/auth";
import type { TokenResponse, UserPublic } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
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
        if (err.status === 403) setError("邮箱域名不在允许列表内");
        else if (err.status === 409) setError("该邮箱已注册");
        else if (err.status === 401) setError("邮箱或密码错误");
        else setError(err.message);
      } else {
        setError("网络错误，请重试");
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
          <h1 className="text-xl font-semibold text-gray-900">KB-Agent</h1>
          <p className="mt-1 text-sm text-gray-500">
            {mode === "login" ? "登录到知识平台" : "注册新账号"}
          </p>
        </div>

        {/* Card */}
        <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-gray-700">邮箱</label>
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
              <label className="mb-1.5 block text-sm font-medium text-gray-700">密码</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
                placeholder="至少 8 位"
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
              {busy ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
            </button>

            {mode === "login" && (
              <p className="text-center text-xs text-gray-400">
                忘记密码？请与{" "}
                <span className="text-gray-600">Palo Alto Networks 渠道团队</span>
                {" "}联系重置密码
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
              {mode === "login" ? "没有账号？去注册" : "已有账号？去登录"}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
