"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
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

export default function WorkspaceAdmin() {
  const t = useTranslations("admin");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [grants, setGrants] = useState<GroupGrant[]>([]);
  const [error, setError] = useState<string | null>(null);

  // 新建空间
  const [showCreate, setShowCreate] = useState(false);
  const [wsName, setWsName] = useState("");

  // 重命名
  const [renaming, setRenaming] = useState(false);
  const [renameVal, setRenameVal] = useState("");
  const renameRef = useRef<HTMLInputElement>(null);

  // 成员 & 组授权
  const [memberId, setMemberId] = useState("");
  const [memberRole, setMemberRole] = useState("viewer");
  const [grantGroup, setGrantGroup] = useState("");
  const [grantRole, setGrantRole] = useState("viewer");

  // 引导问题
  const [sqText, setSqText] = useState("");
  const [sqMsg, setSqMsg] = useState<string | null>(null);

  // 删除流程
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [deleteStep, setDeleteStep] = useState<"confirm" | "download">("confirm");
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

  const loadSq = useCallback(async () => {
    if (!selected) { setSqText(""); return; }
    try {
      const d = await api.get<{ questions: string[] }>(`/settings/workspaces/${selected}/suggested-questions`);
      setSqText(d.questions.join("\n"));
    } catch {
      setSqText("");
    }
    setSqMsg(null);
  }, [selected]);

  useEffect(() => { loadWorkspaces(); loadGroups(); }, [loadWorkspaces, loadGroups]);
  useEffect(() => { loadGrants(); loadSq(); }, [loadGrants, loadSq]);

  // 进入重命名模式时聚焦
  useEffect(() => {
    if (renaming) renameRef.current?.focus();
  }, [renaming]);

  function wrap(fn: () => Promise<void>) {
    return async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      try { await fn(); } catch (err) {
        setError(err instanceof ApiError ? err.message : t("ws_op_failed"));
      }
    };
  }

  const createWs = wrap(async () => {
    await api.post<Workspace>("/workspaces", { name: wsName });
    setWsName("");
    setShowCreate(false);
    await loadWorkspaces();
  });

  const addMember = wrap(async () => {
    if (!selected) return;
    await api.post(`/workspaces/${selected}/members`, { email: memberId, role_in_ws: memberRole });
    setMemberId("");
  });

  const addGrant = wrap(async () => {
    if (!selected || !grantGroup) return;
    await api.post(`/workspaces/${selected}/group-grants`, { group_id: grantGroup, role_in_ws: grantRole });
    await loadGrants();
  });

  async function saveRename() {
    if (!selected || !renameVal.trim()) return;
    setError(null);
    try {
      const ws = await api.patch<Workspace>(`/workspaces/${selected}`, { name: renameVal.trim() });
      setWorkspaces((prev) => prev.map((w) => w.id === selected ? { ...w, name: ws.name } : w));
      setRenaming(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("ws_op_failed"));
    }
  }

  function startRename() {
    const ws = workspaces.find((w) => w.id === selected);
    setRenameVal(ws?.name ?? "");
    setRenaming(true);
  }

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
      if (!res.ok) throw new Error(t("ws_export_failed"));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${selectedWs.name}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setDeleteStep("download");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : t("ws_export_failed"));
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleConfirmDelete() {
    if (!selected) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await api.del(`/workspaces/${selected}`);
      setShowDeleteModal(false);
      setSelected(null);
      await loadWorkspaces();
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : t("ws_delete_failed"));
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <div className="flex gap-6 h-full">
      {/* ── 左栏：空间列表 ── */}
      <aside className="w-52 shrink-0 flex flex-col gap-1">
        <p className="px-1 pb-1 text-xs font-medium text-gray-500 uppercase tracking-wide">
          {t("ws_list_title")}
        </p>
        <ul className="space-y-0.5">
          {workspaces.map((w) => (
            <li key={w.id}>
              <button
                onClick={() => { setSelected(w.id); setRenaming(false); }}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  selected === w.id
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-700 hover:bg-gray-100"
                }`}
              >
                {w.name}
              </button>
            </li>
          ))}
          {workspaces.length === 0 && (
            <li className="px-3 py-2 text-xs text-gray-400">{t("ws_no_workspaces")}</li>
          )}
        </ul>

        {/* 新建空间 */}
        {showCreate ? (
          <form
            onSubmit={createWs}
            className="mt-2 flex flex-col gap-1.5 rounded-lg border bg-white p-2 shadow-sm"
          >
            <input
              value={wsName}
              onChange={(e) => setWsName(e.target.value)}
              placeholder={t("ws_name_placeholder")}
              required
              autoFocus
              className="rounded border px-2 py-1.5 text-sm focus:border-blue-400 focus:outline-none"
            />
            <div className="flex gap-1">
              <button
                type="submit"
                className="flex-1 rounded bg-blue-600 py-1 text-xs text-white hover:bg-blue-700"
              >
                {t("ws_create_btn")}
              </button>
              <button
                type="button"
                onClick={() => { setShowCreate(false); setWsName(""); }}
                className="flex-1 rounded border py-1 text-xs text-gray-600 hover:bg-gray-100"
              >
                {t("ws_cancel_create")}
              </button>
            </div>
          </form>
        ) : (
          <button
            onClick={() => setShowCreate(true)}
            className="mt-2 flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-3 py-2 text-sm text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
          >
            <span className="text-base leading-none">+</span>
            {t("ws_create")}
          </button>
        )}
      </aside>

      {/* ── 右栏：选中空间的配置 ── */}
      <div className="flex-1 min-w-0">
        {!selected ? (
          <div className="flex h-40 items-center justify-center text-sm text-gray-400">
            {t("ws_select_hint")}
          </div>
        ) : (
          <div className="space-y-4">
            {/* 空间名称标题行 */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                {renaming ? (
                  <div className="flex items-center gap-1.5">
                    <input
                      ref={renameRef}
                      value={renameVal}
                      onChange={(e) => setRenameVal(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") { e.preventDefault(); saveRename(); }
                        if (e.key === "Escape") setRenaming(false);
                      }}
                      className="rounded border px-2 py-1 text-sm font-medium focus:border-blue-400 focus:outline-none"
                    />
                    <button
                      onClick={saveRename}
                      title={t("ws_rename_save")}
                      className="rounded p-1 text-green-600 hover:bg-green-50"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                      </svg>
                    </button>
                    <button
                      onClick={() => setRenaming(false)}
                      title={t("ws_rename_cancel")}
                      className="rounded p-1 text-gray-400 hover:bg-gray-100"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <h2 className="truncate text-base font-semibold text-gray-800">
                      {selectedWs?.name}
                    </h2>
                    <button
                      onClick={startRename}
                      title={t("ws_rename_btn")}
                      className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={openDeleteModal}
                className="shrink-0 rounded border border-red-200 px-3 py-1 text-xs text-red-600 hover:bg-red-50"
              >
                {t("ws_delete_btn")}
              </button>
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}

            {/* 成员管理卡片 */}
            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-3 text-sm font-medium text-gray-700">{t("ws_add_member_title")}</h3>
              <form onSubmit={addMember} className="flex gap-2">
                <input
                  type="email"
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  placeholder={t("ws_member_email_placeholder")}
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
                  {t("ws_add_btn")}
                </button>
              </form>

              <div className="mt-4 border-t pt-4">
                <h3 className="mb-1 text-sm font-medium text-gray-700">{t("ws_group_grant_title")}</h3>
                <p className="mb-3 text-xs text-gray-400">{t("ws_group_grant_desc")}</p>
                <form onSubmit={addGrant} className="mb-3 flex gap-2">
                  <select
                    value={grantGroup}
                    onChange={(e) => setGrantGroup(e.target.value)}
                    required
                    className="flex-1 rounded border px-2 py-2 text-sm"
                  >
                    <option value="">{t("ws_group_select")}</option>
                    {groups.map((g) => (
                      <option key={g.id} value={g.id}>{g.name}</option>
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
                    {t("ws_grant_btn")}
                  </button>
                </form>
                <ul className="space-y-1 text-sm text-gray-700">
                  {grants.map((g) => (
                    <li key={g.group_id} className="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5">
                      <span>{groupName(g.group_id)} · {g.role_in_ws}</span>
                      <button
                        onClick={async () => {
                          setError(null);
                          try {
                            await api.del(`/workspaces/${selected}/group-grants/${g.group_id}`);
                            await loadGrants();
                          } catch (err) {
                            setError(err instanceof ApiError ? err.message : t("ws_op_failed"));
                          }
                        }}
                        className="text-xs text-red-500 hover:underline"
                      >
                        {t("ws_revoke")}
                      </button>
                    </li>
                  ))}
                  {grants.length === 0 && <li className="text-gray-400">{t("ws_no_grants")}</li>}
                </ul>
              </div>
            </div>

            {/* 分类体系卡片 */}
            <div className="rounded-lg border bg-white p-4">
              <CategoryManager workspaceId={selected} />
            </div>

            {/* 引导问题卡片 */}
            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-1 text-sm font-medium text-gray-700">{t("ws_sq_title")}</h3>
              <p className="mb-3 text-xs text-gray-400">{t("ws_sq_desc")}</p>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  setError(null);
                  setSqMsg(null);
                  try {
                    const questions = sqText.split("\n").map((q) => q.trim()).filter(Boolean);
                    const updated = await api.put<{ questions: string[] }>(
                      `/settings/workspaces/${selected}/suggested-questions`,
                      { questions }
                    );
                    setSqText(updated.questions.join("\n"));
                    setSqMsg(t("ws_sq_saved", { count: updated.questions.length }));
                  } catch (err) {
                    setError(err instanceof ApiError ? err.message : t("ws_op_failed"));
                  }
                }}
                className="space-y-2"
              >
                <textarea
                  value={sqText}
                  onChange={(e) => setSqText(e.target.value)}
                  rows={4}
                  placeholder={"最近一周有哪些新文档？\n该空间有哪些产品资料？"}
                  className="w-full rounded border px-3 py-2 text-sm font-mono leading-relaxed focus:border-blue-400 focus:outline-none"
                />
                <button
                  type="submit"
                  className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
                >
                  {t("ws_sq_save")}
                </button>
              </form>
              {sqMsg && <p className="mt-2 text-xs text-green-600">{sqMsg}</p>}
            </div>
          </div>
        )}
      </div>

      {/* 删除空间 Modal */}
      {showDeleteModal && selectedWs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 className="mb-1 text-base font-semibold text-red-600">{t("ws_delete_modal_title")}</h2>
            <p className="mb-4 text-sm text-gray-600">
              {t("ws_delete_modal_desc", { name: selectedWs.name })}
            </p>

            {deleteStep === "confirm" && (
              <>
                <p className="mb-2 text-sm text-gray-700">{t("ws_delete_input_hint")}</p>
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
                    {t("ws_cancel_delete")}
                  </button>
                  <button
                    onClick={handleExportAndProceed}
                    disabled={deleteConfirmName !== selectedWs.name || deleteLoading}
                    className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {deleteLoading ? t("ws_delete_exporting") : t("ws_delete_export")}
                  </button>
                </div>
              </>
            )}

            {deleteStep === "download" && (
              <>
                <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
                  {t("ws_delete_download_msg")}
                </div>
                <p className="mb-4 text-sm text-gray-600">{t("ws_delete_download_confirm")}</p>
                {deleteError && <p className="mb-3 text-sm text-red-600">{deleteError}</p>}
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setShowDeleteModal(false)}
                    className="rounded border px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
                  >
                    {t("ws_cancel_delete")}
                  </button>
                  <button
                    onClick={handleExportAndProceed}
                    disabled={deleteLoading}
                    className="rounded border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                  >
                    {t("ws_redownload")}
                  </button>
                  <button
                    onClick={handleConfirmDelete}
                    disabled={deleteLoading}
                    className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {deleteLoading ? t("ws_deleting") : t("ws_confirm_delete")}
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
