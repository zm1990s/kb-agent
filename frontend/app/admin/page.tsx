"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import NavBar from "@/components/NavBar";
import { api, ApiError } from "@/lib/api";
import { isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type { Category, Workspace } from "@/lib/types";

export default function AdminPage() {
  const ready = useAuthGuard();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);

  // 表单状态
  const [wsName, setWsName] = useState("");
  const [catName, setCatName] = useState("");
  const [memberId, setMemberId] = useState("");
  const [memberRole, setMemberRole] = useState("viewer");

  const loadWorkspaces = useCallback(async () => {
    const ws = await api.get<Workspace[]>("/workspaces");
    setWorkspaces(ws);
    if (ws.length > 0 && !selected) setSelected(ws[0].id);
  }, [selected]);

  const loadCategories = useCallback(async () => {
    if (!selected) return;
    try {
      const cats = await api.get<Category[]>(`/categories?workspace=${selected}`);
      setCategories(cats);
    } catch {
      setCategories([]);
    }
  }, [selected]);

  useEffect(() => {
    if (ready && isAdmin()) loadWorkspaces();
  }, [ready, loadWorkspaces]);

  useEffect(() => {
    loadCategories();
  }, [loadCategories]);

  if (!ready) return null;
  if (!isAdmin()) {
    router.replace("/chat");
    return null;
  }

  function wrap(fn: () => Promise<void>) {
    return async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      try {
        await fn();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "操作失败");
      }
    };
  }

  const createWs = wrap(async () => {
    await api.post<Workspace>("/workspaces", { name: wsName });
    setWsName("");
    await loadWorkspaces();
  });

  const addMember = wrap(async () => {
    if (!selected) return;
    await api.post(`/workspaces/${selected}/members`, {
      user_id: memberId,
      role_in_ws: memberRole,
    });
    setMemberId("");
  });

  const createCat = wrap(async () => {
    if (!selected) return;
    await api.post(`/categories?workspace_id=${selected}`, { name: catName });
    setCatName("");
    await loadCategories();
  });

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-6 p-4">
        <h1 className="text-lg font-semibold">空间与成员管理</h1>

        {/* 建空间 */}
        <section className="rounded border bg-white p-4">
          <h2 className="mb-3 text-sm font-medium">创建空间</h2>
          <form onSubmit={createWs} className="flex gap-2">
            <input
              value={wsName}
              onChange={(e) => setWsName(e.target.value)}
              placeholder="空间名称"
              required
              className="flex-1 rounded border px-3 py-2 text-sm"
            />
            <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
              创建
            </button>
          </form>
        </section>

        {/* 选择空间 */}
        <section className="rounded border bg-white p-4">
          <h2 className="mb-3 text-sm font-medium">选择空间</h2>
          <select
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value)}
            className="w-full rounded border px-2 py-1.5 text-sm"
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </section>

        {/* 加成员 */}
        <section className="rounded border bg-white p-4">
          <h2 className="mb-3 text-sm font-medium">添加成员（按 user_id）</h2>
          <form onSubmit={addMember} className="flex gap-2">
            <input
              value={memberId}
              onChange={(e) => setMemberId(e.target.value)}
              placeholder="用户 UUID"
              required
              className="flex-1 rounded border px-3 py-2 text-sm"
            />
            <select
              value={memberRole}
              onChange={(e) => setMemberRole(e.target.value)}
              className="rounded border px-2 text-sm"
            >
              <option value="viewer">viewer</option>
              <option value="editor">editor</option>
              <option value="owner">owner</option>
            </select>
            <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
              添加
            </button>
          </form>
        </section>

        {/* 分类 */}
        <section className="rounded border bg-white p-4">
          <h2 className="mb-3 text-sm font-medium">分类体系</h2>
          <form onSubmit={createCat} className="mb-3 flex gap-2">
            <input
              value={catName}
              onChange={(e) => setCatName(e.target.value)}
              placeholder="新分类名称"
              required
              className="flex-1 rounded border px-3 py-2 text-sm"
            />
            <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
              新建分类
            </button>
          </form>
          <ul className="space-y-1 text-sm text-gray-700">
            {categories.map((c) => (
              <li key={c.id} className="rounded bg-gray-50 px-3 py-1.5">
                {c.name}
              </li>
            ))}
            {categories.length === 0 && (
              <li className="text-gray-400">暂无分类</li>
            )}
          </ul>
        </section>

        {error && <p className="text-sm text-red-600">{error}</p>}
      </main>
    </div>
  );
}
