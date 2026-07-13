"use client";

import { useCallback, useEffect, useState } from "react";
import CategoryManager from "@/components/admin/CategoryManager";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
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

// 空间管理：建空间、选空间、加个人成员、按组授权、导出并删除。
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

  // 删除流程
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [deleteStep, setDeleteStep] = useState<"confirm" | "download" | "done">("confirm");
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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
      email: memberId,
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
  const selectedWs = workspaces.find((w) => w.id === selected);

  function openDeleteModal() {
    setDeleteConfirmName("");
    setDeleteStep("confirm");
    setDeleteError(null);
    setShowDeleteModal(true);
  }

  async function handleExportAndProceed() {
    if (!selected || !selectedWs) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const token = getToken();
      const res = await fetch(`/api/workspaces/${selected}/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("导出失败");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${selectedWs.name}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setDeleteStep("download");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "导出失败");
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleConfirmDelete() {
    if (!selected || !selectedWs) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await api.del(`/workspaces/${selected}`);
      setShowDeleteModal(false);
      setSelected(null);
      await loadWorkspaces();
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "删除失败");
    } finally {
      setDeleteLoading(false);
    }
  }

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
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium">空间授权及配置</h2>
          {selected && (
            <button
              onClick={openDeleteModal}
              className="rounded border border-red-200 px-3 py-1 text-xs text-red-600 hover:bg-red-50"
            >
              删除此空间…
            </button>
          )}
        </div>
        <select
          value={selected ?? ""}
          onChange={(e) => setSelected(e.target.value)}
          className="mb-5 w-full rounded border px-2 py-1.5 text-sm"
        >
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>

        <div className="border-t pt-4">
          <h3 className="mb-3 text-xs font-medium text-gray-600">添加个人成员</h3>
          <form onSubmit={addMember} className="flex gap-2">
            <input
              type="email"
              value={memberId}
              onChange={(e) => setMemberId(e.target.value)}
              placeholder="用户邮箱"
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
        </div>

        <div className="border-t pt-4 mt-4">
          <h3 className="mb-1 text-xs font-medium text-gray-600">按用户组授权</h3>
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
        </div>

        <div className="border-t pt-4 mt-4">
          <CategoryManager workspaceId={selected} />
        </div>
      </section>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* 删除空间 Modal */}
      {showDeleteModal && selectedWs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="mb-1 text-base font-semibold text-red-600">删除空间</h2>
            <p className="mb-4 text-sm text-gray-600">
              此操作将永久删除空间「<strong>{selectedWs.name}</strong>」及其全部文档、对话记录，无法恢复。
            </p>

            {deleteStep === "confirm" && (
              <>
                <p className="mb-2 text-sm text-gray-700">
                  请输入空间名称确认：
                </p>
                <input
                  value={deleteConfirmName}
                  onChange={(e) => setDeleteConfirmName(e.target.value)}
                  placeholder={selectedWs.name}
                  className="mb-4 w-full rounded border px-3 py-2 text-sm focus:border-red-400 focus:outline-none"
                />
                {deleteError && <p className="mb-3 text-sm text-red-600">{deleteError}</p>}
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setShowDeleteModal(false)}
                    className="rounded border px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleExportAndProceed}
                    disabled={deleteConfirmName !== selectedWs.name || deleteLoading}
                    className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {deleteLoading ? "打包中…" : "导出所有文件并继续"}
                  </button>
                </div>
              </>
            )}

            {deleteStep === "download" && (
              <>
                <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
                  文件已开始下载。请确认下载完成后再执行删除。
                </div>
                <p className="mb-4 text-sm text-gray-600">
                  下载完成了吗？点击"确认删除"将永久删除该空间。
                </p>
                {deleteError && <p className="mb-3 text-sm text-red-600">{deleteError}</p>}
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setShowDeleteModal(false)}
                    className="rounded border px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
                  >
                    取消，不删除
                  </button>
                  <button
                    onClick={handleExportAndProceed}
                    disabled={deleteLoading}
                    className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                  >
                    重新下载
                  </button>
                  <button
                    onClick={handleConfirmDelete}
                    disabled={deleteLoading}
                    className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {deleteLoading ? "删除中…" : "确认删除"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
