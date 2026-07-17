"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";

interface Props {
  value: string | null;
  onChange: (id: string) => void;
  onWorkspaceChange?: (ws: Workspace) => void;
}

// 空间下拉选择器。加载当前用户可见空间；无空间时提示。
export default function WorkspacePicker({ value, onChange, onWorkspaceChange }: Props) {
  const t = useTranslations("workspacePicker");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<Workspace[]>("/workspaces")
      .then((ws) => {
        setWorkspaces(ws);
        if (ws.length === 0) return;
        // 若缓存的 value 不在列表中（如 DB 重建后旧 ID 失效），自动切换到第一个
        const valid = ws.some((w) => w.id === value);
        if (!valid) onChange(ws[0].id);
        // 通知父组件当前选中的空间对象（含 role_in_ws）
        const current = ws.find((w) => w.id === (valid ? value : ws[0].id));
        if (current) onWorkspaceChange?.(current);
      })
      .finally(() => setLoading(false));
  }, [onChange, value]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <span className="text-sm text-gray-400">{t("loading")}</span>;
  if (workspaces.length === 0)
    return <span className="text-sm text-gray-500">{t("no_workspaces")}</span>;

  return (
    <select
      value={value ?? ""}
      onChange={(e) => {
        onChange(e.target.value);
        const ws = workspaces.find((w) => w.id === e.target.value);
        if (ws) onWorkspaceChange?.(ws);
      }}
      className="rounded border px-2 py-1.5 text-sm"
    >
      {workspaces.map((w) => (
        <option key={w.id} value={w.id}>
          {w.name}
        </option>
      ))}
    </select>
  );
}
