"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Workspace } from "@/lib/types";

interface Group {
  id: string;
  name: string;
}
interface GroupGrant {
  workspace_id: string;
  group_id: string;
  role_in_ws: string;
}

// 空间管理：建空间、选空间、加个人成员、按组授权（F7）。分类已移到系统设置。
export default function WorkspaceAdmin() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [grants, setGrants] = useState<GroupGrant[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [wsName, setWsName] = useState("");
  const [memberId, setMemberId] = useState("");
  const [memberRole, setMemberRole] = useState("viewer");
  const [grantGroup, setGrantGroup] = useState("");
  const [grantRole, setGrantRole] = useState("viewer");

  const loadWorkspaces = useCallback(async () => {
    const ws = await api.get<Workspace[]>("/workspaces");
    setWorkspaces(ws);
    setSelected((cur) => cur ?? (ws.length > 0 ? ws[0].id : null));
  }, []);

  const loadGroups = useCallback(async () => {
    try {
      setGroups(await api.get<Group[]>("/admin/groups"));
    } catch {
      setGroups([]);
    }
  }, []);

  const loadGrants = useCallback(async () => {
    if (!selected) return;
    try {
      setGrants(await api.get<GroupGrant[]>(`/workspaces/${selected}/group-grants`));
    } catch {
      setGrants([]);
    }
  }, [selected]);

  useEffect(() => {
    loadWorkspaces();
    loadGroups();
  }, [loadWorkspaces, loadGroups]);
  useEffect(() => {
    loadGrants();
  }, [loadGrants]);

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
  const addGrant = wrap(async () => {
    if (!selected || !grantGroup) return;
    await api.post(`/workspaces/${selected}/group-grants`, {
      group_id: grantGroup,
      role_in_ws: grantRole,
    });
    await loadGrants();
  });

  const groupName = (id: string) => groups.find((g) => g.id === id)?.name ?? id;

  return (
    <div className="space-y-6">
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

      <section className="rounded border bg-white p-4">
        <h2 className="mb-3 text-sm font-medium">添加个人成员（按 user_id）</h2>
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

      <section className="rounded border bg-white p-4">
        <h2 className="mb-1 text-sm font-medium">按用户组授权（F7）</h2>
        <p className="mb-3 text-xs text-gray-400">
          授权给组后，组内成员自动获得该空间访问权（与个人成员并存）。
        </p>
        <form onSubmit={addGrant} className="mb-3 flex gap-2">
          <select
            value={grantGroup}
            onChange={(e) => setGrantGroup(e.target.value)}
            required
            className="flex-1 rounded border px-2 py-2 text-sm"
          >
            <option value="">选择用户组…</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
          <select
            value={grantRole}
            onChange={(e) => setGrantRole(e.target.value)}
            className="rounded border px-2 text-sm"
          >
            <option value="viewer">viewer</option>
            <option value="editor">editor</option>
            <option value="owner">owner</option>
          </select>
          <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
            授权
          </button>
        </form>
        <ul className="space-y-1 text-sm text-gray-700">
          {grants.map((g) => (
            <li
              key={g.group_id}
              className="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5"
            >
              <span>
                {groupName(g.group_id)} · {g.role_in_ws}
              </span>
              <button
                onClick={async () => {
                  setError(null);
                  try {
                    await api.del(
                      `/workspaces/${selected}/group-grants/${g.group_id}`
                    );
                    await loadGrants();
                  } catch (err) {
                    setError(err instanceof ApiError ? err.message : "撤销失败");
                  }
                }}
                className="text-xs text-red-500 hover:underline"
              >
                撤销
              </button>
            </li>
          ))}
          {grants.length === 0 && <li className="text-gray-400">暂无组授权</li>}
        </ul>
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
