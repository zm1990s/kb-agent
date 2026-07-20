"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import FolderTree, { buildTree } from "@/components/FolderTree";
import WorkspacePicker from "@/components/WorkspacePicker";
import type { Folder, Workspace } from "@/lib/types";

interface Props {
  conversationId: string | null;
  filename: string;
  relpath?: string;
  canWrite?: boolean;
}

// 可保存进文档库的成果文件后缀（与后端 _SAVEABLE_DOC_SUFFIXES 保持一致）
const SAVEABLE_SUFFIXES = [
  ".md", ".markdown", ".txt", ".csv",
  ".pdf", ".png", ".jpg", ".jpeg",
  ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
];

function isSaveableDoc(name: string): boolean {
  const lower = name.toLowerCase();
  return SAVEABLE_SUFFIXES.some((s) => lower.endsWith(s));
}

// 逐段编码相对路径，保留 / 作为分隔符（供 {file_path:path} 端点）
function encodePath(p: string): string {
  return p.split("/").map(encodeURIComponent).join("/");
}

const NO_OP = () => {};

export default function SaveToWorkspaceButton({
  conversationId,
  filename,
  relpath,
  canWrite = true,
}: Props) {
  const t = useTranslations("chatComponents");
  const [open, setOpen] = useState(false);
  const [wsId, setWsId] = useState<string | null>(null);
  const [wsRole, setWsRole] = useState<string | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (!isSaveableDoc(filename) || !canWrite) return null;

  function openDialog() {
    setWsId(null);
    setWsRole(null);
    setFolders([]);
    setFolderId(null);
    setMsg(null);
    setDone(false);
    setOpen(true);
  }

  const onWorkspaceChange = useCallback(async (ws: Workspace) => {
    setWsRole(ws.role_in_ws);
    setFolderId(null);
    setLoadingFolders(true);
    try {
      const fs = await api.get<Folder[]>(`/folders?workspace=${ws.id}`);
      setFolders(fs);
    } catch {
      setFolders([]);
    } finally {
      setLoadingFolders(false);
    }
  }, []);

  const handleWsChange = useCallback((id: string | null) => {
    setWsId(id);
    if (id === null) {
      setWsRole(null);
      setFolders([]);
      setFolderId(null);
    }
  }, []);

  const canSaveHere = wsId !== null && (wsRole === "owner" || wsRole === "editor");

  async function submit() {
    if (!conversationId || !wsId) return;
    setSaving(true);
    setMsg(null);
    try {
      await api.post(
        `/chat/plus/conversations/${conversationId}/files/${encodePath(relpath ?? filename)}/save-to-library`,
        { workspace_id: wsId, folder_id: folderId }
      );
      setDone(true);
      setTimeout(() => setOpen(false), 1200);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={openDialog}
        className="flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-xs text-emerald-700 hover:bg-emerald-100 transition-colors"
        title={t("saveToLibrary")}
      >
        <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="currentColor">
          <path d="M3 5a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2V5z" />
        </svg>
        {t("saveToLibrary")}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h2 className="mb-1 text-lg font-semibold text-gray-900">{t("saveToLibrary")}</h2>
            <p className="mb-4 text-xs text-gray-500">
              {t("saveToLibrarySourceLabel")}
              <span className="font-mono">{relpath ?? filename}</span>
            </p>

            {done ? (
              <p className="py-6 text-center text-sm text-green-600">{t("savedToLibrary")}</p>
            ) : (
              <>
                <div className="mb-3 text-sm">
                  <span className="mb-1 block text-gray-700">{t("saveToLibrarySelectWs")}</span>
                  <WorkspacePicker
                    value={wsId}
                    onChange={handleWsChange}
                    onWorkspaceChange={onWorkspaceChange}
                  />
                </div>

                {wsId !== null && !canSaveHere && (
                  <p className="mb-3 text-sm text-amber-600">{t("saveToLibraryNoPerm")}</p>
                )}

                {canSaveHere && (
                  <div className="mb-3 text-sm">
                    <span className="mb-1 block text-gray-700">{t("saveToLibrarySelectFolder")}</span>
                    <div className="max-h-48 overflow-y-auto rounded-lg border border-gray-200 p-1">
                      <button
                        type="button"
                        onClick={() => setFolderId(null)}
                        className={`w-full rounded px-2 py-1 text-left text-sm ${
                          folderId === null ? "bg-emerald-50 text-emerald-700" : "text-gray-600 hover:bg-gray-50"
                        }`}
                      >
                        {t("saveToLibraryRoot")}
                      </button>
                      {loadingFolders ? (
                        <p className="px-2 py-1 text-xs text-gray-400">{t("saving")}</p>
                      ) : (
                        <FolderTree
                          nodes={buildTree(folders)}
                          activeId={folderId ?? ""}
                          admin={false}
                          onSelect={setFolderId}
                          onAddChild={NO_OP}
                          onRename={NO_OP}
                          onDelete={NO_OP}
                        />
                      )}
                    </div>
                  </div>
                )}

                {msg && <p className="mb-3 text-sm text-red-500">{msg}</p>}

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
                  >
                    {t("cancel")}
                  </button>
                  <button
                    type="button"
                    onClick={submit}
                    disabled={saving || !canSaveHere}
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
                  >
                    {saving ? t("saving") : t("saveToLibraryConfirm")}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
