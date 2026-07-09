"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

interface Props {
  onClose: () => void;
}

export default function ChangePasswordModal({ onClose }: Props) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (next !== confirm) {
      setError("两次输入的新密码不一致");
      return;
    }
    if (next.length < 8) {
      setError("新密码至少 8 位");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "修改失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-full max-w-sm rounded-lg border bg-white p-6 shadow-lg">
        <h2 className="mb-4 text-base font-semibold">修改密码</h2>
        {success ? (
          <div className="space-y-4">
            <p className="text-sm text-green-600">密码已修改成功。</p>
            <button
              onClick={onClose}
              className="w-full rounded bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              关闭
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-gray-500">当前密码</label>
              <input
                type="password"
                required
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                className="w-full rounded border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">新密码（至少 8 位）</label>
              <input
                type="password"
                required
                minLength={8}
                value={next}
                onChange={(e) => setNext(e.target.value)}
                className="w-full rounded border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">确认新密码</label>
              <input
                type="password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            {error && <p className="text-xs text-red-600">{error}</p>}
            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={loading}
                className="flex-1 rounded bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? "保存中…" : "保存"}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="flex-1 rounded border py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                取消
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
