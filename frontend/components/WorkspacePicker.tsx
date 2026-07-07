"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";

interface Props {
  value: string | null;
  onChange: (id: string) => void;
}

// 空间下拉选择器。加载当前用户可见空间；无空间时提示。
export default function WorkspacePicker({ value, onChange }: Props) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<Workspace[]>("/workspaces")
      .then((ws) => {
        setWorkspaces(ws);
        if (ws.length > 0 && !value) onChange(ws[0].id);
      })
      .finally(() => setLoading(false));
  }, [onChange, value]);

  if (loading) return <span className="text-sm text-gray-400">加载空间…</span>;
  if (workspaces.length === 0)
    return <span className="text-sm text-gray-500">暂无可用空间</span>;

  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
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
