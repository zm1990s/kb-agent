"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import NavBar from "@/components/NavBar";
import { api, ApiError } from "@/lib/api";
import { clearAuth, getEmail, isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";

export default function AccountPage() {
  const t = useTranslations("account");
  const ready = useAuthGuard();
  const router = useRouter();
  const email = getEmail();
  const admin = isAdmin();

  // 修改密码
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdError, setPwdError] = useState<string | null>(null);
  const [pwdSuccess, setPwdSuccess] = useState(false);
  const [pwdLoading, setPwdLoading] = useState(false);

  // 注销
  const [showDelete, setShowDelete] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (!ready) return null;

  async function submitPassword(e: React.FormEvent) {
    e.preventDefault();
    setPwdError(null);
    if (next !== confirmPwd) { setPwdError(t("err_mismatch")); return; }
    if (next.length < 8) { setPwdError(t("err_too_short")); return; }
    setPwdLoading(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      setPwdSuccess(true);
      setCurrent(""); setNext(""); setConfirmPwd("");
    } catch (err) {
      setPwdError(err instanceof ApiError ? err.message : t("change_failed"));
    } finally {
      setPwdLoading(false);
    }
  }

  async function confirmDelete() {
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await api.del("/auth/me");
      clearAuth();
      router.replace("/login");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : t("deactivate_failed"));
      setDeleteLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <NavBar />
      <main className="mx-auto w-full max-w-lg flex-1 px-4 py-8">
        <h1 className="mb-6 text-lg font-semibold text-gray-900">{t("title")}</h1>

        {/* 基本信息 */}
        <section className="mb-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-3 text-sm font-medium text-gray-700">{t("basic_info")}</h2>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
              {(email ?? "U")[0].toUpperCase()}
            </div>
            <div>
              <p className="text-sm font-medium text-gray-900">{email ?? "—"}</p>
              <p className="text-xs text-gray-400">{admin ? t("admin_role") : t("user_role")}</p>
            </div>
          </div>
        </section>

        {/* 修改密码 */}
        <section className="mb-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-sm font-medium text-gray-700">{t("change_password")}</h2>
          {pwdSuccess ? (
            <div className="flex items-center gap-2 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">
              <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              {t("password_success")}
              <button onClick={() => setPwdSuccess(false)} className="ml-auto text-xs text-green-600 underline">
                {t("modify_again")}
              </button>
            </div>
          ) : (
            <form onSubmit={submitPassword} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-600">{t("current_password")}</label>
                <input
                  type="password"
                  required
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-600">{t("new_password")}</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-600">{t("confirm_password")}</label>
                <input
                  type="password"
                  required
                  value={confirmPwd}
                  onChange={(e) => setConfirmPwd(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                />
              </div>
              {pwdError && (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {pwdError}
                </p>
              )}
              <button
                type="submit"
                disabled={pwdLoading}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {pwdLoading ? t("saving") : t("save_password")}
              </button>
            </form>
          )}
        </section>

        {/* 注销账号 */}
        {!admin && (
          <section className="rounded-xl border border-red-100 bg-white p-6 shadow-sm">
            <h2 className="mb-1 text-sm font-medium text-gray-700">{t("deactivate")}</h2>
            <p className="mb-4 text-xs text-gray-500">
              {t("deactivate_desc")}
            </p>
            {!showDelete ? (
              <button
                onClick={() => setShowDelete(true)}
                className="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
              >
                {t("deactivate_btn")}
              </button>
            ) : (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="mb-3 text-sm text-red-700">{t("deactivate_confirm", { email: email ?? "" })}</p>
                {deleteError && (
                  <p className="mb-2 text-xs text-red-700">{deleteError}</p>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowDelete(false)}
                    disabled={deleteLoading}
                    className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
                  >
                    {t("cancel")}
                  </button>
                  <button
                    onClick={confirmDelete}
                    disabled={deleteLoading}
                    className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                  >
                    {deleteLoading ? t("processing") : t("confirm_deactivate")}
                  </button>
                </div>
              </div>
            )}
            {admin && (
              <p className="text-xs text-gray-400">{t("admin_cannot_deactivate")}</p>
            )}
          </section>
        )}
        {admin && (
          <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h2 className="mb-1 text-sm font-medium text-gray-700">{t("deactivate")}</h2>
            <p className="text-xs text-gray-400">{t("admin_cannot_deactivate")}</p>
          </section>
        )}
      </main>
    </div>
  );
}
