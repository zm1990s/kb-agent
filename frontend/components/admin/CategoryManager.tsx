"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import type { Category, Workspace } from "@/lib/types";

interface Props {
  workspaceId?: string | null;
}

export default function CategoryManager({ workspaceId: externalId }: Props) {
  const t = useTranslations("admin");
  // 独立使用时自己管理空间选择；嵌入 WorkspaceAdmin 时直接继承外部选中空间
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [internalId, setInternalId] = useState<string | null>(null);
  const selected = externalId ?? internalId;

  const [categories, setCategories] = useState<Category[]>([]);
  const [catName, setCatName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadWorkspaces = useCallback(async () => {
    if (externalId !== undefined) return; // 外部托管，不需要自己拉空间列表
    const ws = await api.get<Workspace[]>("/workspaces");
    setWorkspaces(ws);
    setInternalId((cur) => cur ?? (ws.length > 0 ? ws[0].id : null));
  }, [externalId]);

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
      setError(err instanceof ApiError ? err.message : t("cat_create_failed"));
    }
  }

  return (
    <section className={externalId !== undefined ? "" : "rounded border bg-white p-4"}>
      <h2 className="mb-1 text-sm font-medium">{t("cat_title")}</h2>
      <p className="mb-3 text-xs text-gray-400">
        {t("cat_desc")}
      </p>
      {externalId === undefined && (
        <div className="mb-3">
          <select
            value={selected ?? ""}
            onChange={(e) => setInternalId(e.target.value)}
            className="w-full rounded border px-2 py-1.5 text-sm"
          >
            {workspaces.length === 0 && <option value="">{t("cat_no_workspaces")}</option>}
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <form onSubmit={createCat} className="mb-3 flex gap-2">
        <input
          value={catName}
          onChange={(e) => setCatName(e.target.value)}
          placeholder={t("cat_name_placeholder")}
          required
          className="flex-1 rounded border px-3 py-2 text-sm"
        />
        <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
          {t("cat_create_btn")}
        </button>
      </form>
      <ul className="space-y-1 text-sm text-gray-700">
        {categories.map((c) => (
          <li key={c.id} className="rounded bg-gray-50 px-3 py-1.5">
            {c.name}
          </li>
        ))}
        {categories.length === 0 && <li className="text-gray-400">{t("cat_none")}</li>}
      </ul>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </section>
  );
}
