"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";

interface Props {
  value: string | null;
  onChange: (id: string | null) => void;
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
        // value=null 表示"自动"模式，保持不变；仅在缓存 ID 已失效时重置为 null（自动模式）
        if (value !== null) {
          const valid = ws.some((w) => w.id === value);
          if (!valid) onChange(null);
        }
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
        onChange(e.target.value || null);
        const ws = e.target.value ? workspaces.find((w) => w.id === e.target.value) : undefined;
        if (ws) onWorkspaceChange?.(ws);
      }}
      className="rounded border px-2 py-1.5 text-sm"
    >
      <option value="">{t("auto")}</option>
      {workspaces.map((w) => (
        <option key={w.id} value={w.id}>
          {w.name}
        </option>
      ))}
    </select>
  );
}
