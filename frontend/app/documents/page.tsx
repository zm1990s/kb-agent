"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import FolderTree, { buildTree } from "@/components/FolderTree";
import NavBar from "@/components/NavBar";
import TaskLogPanel from "@/components/TaskLogPanel";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken, isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type { DocumentPublic, Folder } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  processing: "归类中",
  ready: "已就绪",
  failed: "失败",
};

// 特殊过滤值：全部 / 未归目录
const ALL = "__all__";
const ROOT = "__root__";

export default function DocumentsPage() {
  const ready = useAuthGuard();
  const admin = isAdmin();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [activeFolder, setActiveFolder] = useState<string>(ALL);
  const [docs, setDocs] = useState<DocumentPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const replaceRef = useRef<HTMLInputElement>(null);
  const [replacingId, setReplacingId] = useState<string | null>(null);
  // 正在查看日志的文档
  const [logDoc, setLogDoc] = useState<DocumentPublic | null>(null);

  const loadFolders = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setFolders(await api.get<Folder[]>(`/folders?workspace=${workspaceId}`));
    } catch {
      setFolders([]);
    }
  }, [workspaceId]);

  const loadDocs = useCallback(async () => {
    if (!workspaceId) return;
    try {
      let url = `/workspaces/${workspaceId}/documents`;
      if (activeFolder !== ALL && activeFolder !== ROOT) {
        url += `?folder=${activeFolder}`;
      }
      let list = await api.get<DocumentPublic[]>(url);
      if (activeFolder === ROOT) list = list.filter((d) => !d.folder_id);
      setDocs(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, [workspaceId, activeFolder]);

  useEffect(() => {
    setActiveFolder(ALL);
    loadFolders();
  }, [workspaceId, loadFolders]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  useEffect(() => {
    if (!docs.some((d) => d.status === "processing")) return;
    const t = setInterval(loadDocs, 3000);
    return () => clearInterval(t);
  }, [docs, loadDocs]);

  if (!ready) return null;

  const folderName = (id: string | null) =>
    folders.find((f) => f.id === id)?.name ?? "—";

  async function createFolder(parentId: string | null) {
    const name = window.prompt(parentId ? "新建子目录名称" : "新目录名称");
    if (!name || !workspaceId) return;
    setError(null);
    try {
      await api.post(`/folders?workspace_id=${workspaceId}`, {
        name,
        parent_id: parentId,
      });
      await loadFolders();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "建目录失败");
    }
  }

  async function renameFolder(folder: Folder) {
    const name = window.prompt("重命名目录", folder.name);
    if (!name || !workspaceId || name === folder.name) return;
    setError(null);
    try {
      await api.patch(`/folders/${folder.id}?workspace_id=${workspaceId}`, {
        name,
      });
      await loadFolders();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "重命名失败");
    }
  }

  async function deleteFolder(id: string) {
    if (
      !workspaceId ||
      !window.confirm("删除该目录？子目录一并删除，其下文档移出目录（不删除文档）。")
    )
      return;
    try {
      await api.del(`/folders/${id}?workspace_id=${workspaceId}`);
      if (activeFolder === id) setActiveFolder(ALL);
      await loadFolders();
      await loadDocs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除目录失败");
    }
  }

  // 拖拽落到目录：文档→移动到目录；目录→改父级
  async function onDropItem(
    targetFolderId: string | null,
    payload: { type: "doc" | "folder"; id: string }
  ) {
    if (!workspaceId) return;
    setError(null);
    try {
      if (payload.type === "doc") {
        await api.patch(`/documents/${payload.id}/move`, {
          folder_id: targetFolderId,
        });
        await loadDocs();
      } else {
        await api.patch(
          `/folders/${payload.id}/move?workspace_id=${workspaceId}`,
          { parent_id: targetFolderId }
        );
        await loadFolders();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "移动失败");
    }
  }

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !workspaceId) return;
    setError(null);
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      // 当前选中具体目录时，上传即归入该目录
      if (activeFolder !== ALL && activeFolder !== ROOT) {
        form.append("folder_id", activeFolder);
      }
      await api.upload(`/workspaces/${workspaceId}/documents`, form);
      if (fileRef.current) fileRef.current.value = "";
      await loadDocs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function deleteDoc(doc: DocumentPublic) {
    if (!window.confirm(`删除文档「${doc.title}」？此操作不可撤销。`)) return;
    setError(null);
    try {
      await api.del(`/documents/${doc.id}`);
      await loadDocs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  async function reprocessDoc(doc: DocumentPublic) {
    setError(null);
    try {
      await api.post(`/documents/${doc.id}/reprocess`);
      await loadDocs(); // 状态回到归类中，轮询会自动刷新
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "重试失败");
    }
  }

  function triggerReplace(docId: string) {
    setReplacingId(docId);
    replaceRef.current?.click();
  }

  async function onReplacePicked() {
    const file = replaceRef.current?.files?.[0];
    if (!file || !replacingId) return;
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.upload(`/documents/${replacingId}/replace`, form);
      if (replaceRef.current) replaceRef.current.value = "";
      setReplacingId(null);
      await loadDocs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "替换失败");
    }
  }

  async function download(doc: DocumentPublic) {
    try {
      const token = getToken();
      const res = await fetch(`/api/documents/${doc.id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.title;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("下载失败");
    }
  }

  return (
    <div className="flex h-screen flex-col">
      <NavBar />
      <div className="flex items-center gap-3 border-b bg-white px-4 py-2">
        <span className="text-sm text-gray-500">空间：</span>
        <WorkspacePicker value={workspaceId} onChange={setWorkspaceId} />
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 目录树 */}
        <aside className="flex w-56 shrink-0 flex-col border-r bg-white">
          {admin && (
            <button
              onClick={() => createFolder(null)}
              className="m-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              + 新建顶级目录
            </button>
          )}
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {[
              { id: ALL, name: "全部文档" },
              { id: ROOT, name: "未归目录" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setActiveFolder(f.id)}
                className={`block w-full rounded px-3 py-2 text-left text-sm ${
                  activeFolder === f.id
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                {f.name}
              </button>
            ))}
            <div className="my-1 border-t" />
            <FolderTree
              nodes={buildTree(folders)}
              activeId={activeFolder}
              admin={admin}
              onSelect={setActiveFolder}
              onAddChild={(parentId) => createFolder(parentId)}
              onRename={renameFolder}
              onDelete={deleteFolder}
              onDropItem={admin ? onDropItem : undefined}
            />
            {admin && (
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const raw = e.dataTransfer.getData("application/kb-item");
                  if (raw) onDropItem(null, JSON.parse(raw));
                }}
                className="mt-1 rounded border border-dashed border-gray-300 px-3 py-2 text-center text-xs text-gray-400"
              >
                拖到此处移出目录 / 置为顶级
              </div>
            )}
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-4">
          {admin && (
            <form
              onSubmit={onUpload}
              className="mb-4 flex items-center gap-3 rounded border bg-white p-4"
            >
              <input ref={fileRef} type="file" className="text-sm" required />
              <button
                type="submit"
                disabled={uploading || !workspaceId}
                className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {uploading ? "上传中…" : "上传文档"}
              </button>
              {activeFolder !== ALL && activeFolder !== ROOT && (
                <span className="text-xs text-gray-400">
                  上传到目录：{folderName(activeFolder)}
                </span>
              )}
            </form>
          )}

          {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

          {/* 隐藏的替换文件选择器 */}
          <input
            ref={replaceRef}
            type="file"
            className="hidden"
            onChange={onReplacePicked}
          />

          <div className="overflow-hidden rounded border bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-500">
                <tr>
                  <th className="px-4 py-2">标题</th>
                  <th className="px-4 py-2">目录</th>
                  <th className="px-4 py-2">状态</th>
                  <th className="px-4 py-2">摘要</th>
                  <th className="px-4 py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {docs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-gray-400">
                      暂无文档
                    </td>
                  </tr>
                )}
                {docs.map((d) => (
                  <tr
                    key={d.id}
                    className="border-t align-top"
                    draggable={admin}
                    onDragStart={(e) =>
                      e.dataTransfer.setData(
                        "application/kb-item",
                        JSON.stringify({ type: "doc", id: d.id })
                      )
                    }
                  >
                    <td className="px-4 py-2">
                      {admin && <span className="mr-1 cursor-grab text-gray-300">⠿</span>}
                      {d.title}
                    </td>
                    <td className="px-4 py-2">
                      {admin ? (
                        <select
                          value={d.folder_id ?? ""}
                          onChange={async (e) => {
                            setError(null);
                            try {
                              await api.patch(`/documents/${d.id}/move`, {
                                folder_id: e.target.value || null,
                              });
                              await loadDocs();
                            } catch (err) {
                              setError(
                                err instanceof ApiError ? err.message : "移动失败"
                              );
                            }
                          }}
                          className="rounded border px-1 py-0.5 text-xs"
                        >
                          <option value="">（无目录）</option>
                          {folders.map((f) => (
                            <option key={f.id} value={f.id}>
                              {f.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="text-gray-500">{folderName(d.folder_id)}</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={
                          d.status === "ready"
                            ? "text-green-700"
                            : d.status === "failed"
                              ? "text-red-600"
                              : "text-amber-600"
                        }
                      >
                        {STATUS_LABEL[d.status] ?? d.status}
                      </span>
                    </td>
                    <td className="max-w-xs truncate px-4 py-2 text-gray-600">
                      {d.summary ?? "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2">
                      <button
                        onClick={() => download(d)}
                        className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-blue-700 hover:bg-gray-200"
                      >
                        下载
                      </button>
                      <button
                        onClick={() => setLogDoc(d)}
                        className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                      >
                        详情
                      </button>
                      {admin && d.status === "failed" && (
                        <button
                          onClick={() => reprocessDoc(d)}
                          className="mr-1 rounded bg-amber-100 px-2 py-1 text-xs text-amber-700 hover:bg-amber-200"
                        >
                          重试
                        </button>
                      )}
                      {admin && (
                        <>
                          <button
                            onClick={() => triggerReplace(d.id)}
                            className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                          >
                            替换
                          </button>
                          <button
                            onClick={() => deleteDoc(d)}
                            className="rounded bg-gray-100 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                          >
                            删除
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </main>
      </div>

      {logDoc && (
        <TaskLogPanel
          documentId={logDoc.id}
          title={logDoc.title}
          onClose={() => setLogDoc(null)}
        />
      )}
    </div>
  );
}
