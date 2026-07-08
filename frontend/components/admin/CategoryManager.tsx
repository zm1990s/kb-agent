"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Category, Workspace } from "@/lib/types";

// 分类体系管理（F8：从空间管理移到系统设置）。按空间维护 Agent 归类分类。
export default function CategoryManager() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [catName, setCatName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadWorkspaces = useCallback(async () => {
    const ws = await api.get<Workspace[]>("/workspaces");
    setWorkspaces(ws);
    setSelected((cur) => cur ?? (ws.length > 0 ? ws[0].id : null));
  }, []);

  const loadCategories = useCallback(async () => {
    if (!selected) return;
    try {
      setCategories(await api.get<Category[]>(`/categories?workspace=${selected}`));
    } catch {
      setCategories([]);
    }
  }, [selected]);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);
  useEffect(() => {
    loadCategories();
  }, [loadCategories]);

  async function createCat(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setError(null);
    try {
      await api.post(`/categories?workspace_id=${selected}`, { name: catName });
      setCatName("");
      await loadCategories();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "新建分类失败");
    }
  }

  return (
    <section className="rounded border bg-white p-4">
      <h2 className="mb-1 text-sm font-medium">分类体系</h2>
      <p className="mb-3 text-xs text-gray-400">
        管理员预定义分类，Agent 归类时归入最匹配的分类。按空间维护。
      </p>
      <div className="mb-3">
        <select
          value={selected ?? ""}
          onChange={(e) => setSelected(e.target.value)}
          className="w-full rounded border px-2 py-1.5 text-sm"
        >
          {workspaces.length === 0 && <option value="">（暂无空间）</option>}
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      </div>
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
        {categories.length === 0 && <li className="text-gray-400">暂无分类</li>}
      </ul>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  );
}
