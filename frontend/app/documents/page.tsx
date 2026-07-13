"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import FolderTree, { buildTree } from "@/components/FolderTree";
import Markdown from "@/components/Markdown";
import NavBar from "@/components/NavBar";
import TaskLogPanel from "@/components/TaskLogPanel";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken, isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type { Category, DocumentPublic, Folder } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  processing: "归类中",
  ready: "已就绪",
  failed: "失败",
};

// 规范化文件/目录名：空格→_, 控制字符移除, 合并连续下划线
function sanitizeName(name: string): string {
  return name
    .replace(/[\x00-\x1f\x7f]/g, "")
    .replace(/[ \t]+/g, "_")
    .replace(/[/\\]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "") || "untitled";
}

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
  const dirRef = useRef<HTMLInputElement>(null);
  const replaceRef = useRef<HTMLInputElement>(null);
  const [replacingId, setReplacingId] = useState<string | null>(null);
  // 正在查看日志的文档
  const [logDoc, setLogDoc] = useState<DocumentPublic | null>(null);
  // 文件详情弹窗
  const [detailDoc, setDetailDoc] = useState<DocumentPublic | null>(null);
  // 预览
  const [previewDoc, setPreviewDoc] = useState<DocumentPublic | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  // 分类名映射（展示用）
  const [categories, setCategories] = useState<Category[]>([]);
  // 搜索关键词
  const [query, setQuery] = useState("");
  // 点击标签快速过滤
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  // 自定义展示列
  const [cols, setCols] = useState<Record<string, boolean>>({
    folder: true,
    category: true,
    tags: true,
    type: false,
    status: true,
    summary: true,
    created: false,
  });

  const loadFolders = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setFolders(await api.get<Folder[]>(`/folders?workspace=${workspaceId}`));
    } catch {
      setFolders([]);
    }
    try {
      setCategories(await api.get<Category[]>(`/categories?workspace=${workspaceId}`));
    } catch {
      setCategories([]); // 非管理员无权列分类，降级为空
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
  const categoryName = (id: string | null) =>
    categories.find((c) => c.id === id)?.name ?? "—";

  // 客户端搜索：标题/摘要/标签/分类名
  const q = query.trim().toLowerCase();
  const shownDocs = docs.filter((d) => {
    if (tagFilter && !(d.tags ?? []).includes(tagFilter)) return false;
    if (!q) return true;
    const hay = [
      d.title,
      d.summary ?? "",
      (d.tags ?? []).join(" "),
      categoryName(d.category_id),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });

  const COLS: { key: string; label: string }[] = [
    { key: "folder", label: "目录" },
    { key: "category", label: "分类" },
    { key: "tags", label: "标签" },
    { key: "type", label: "类型" },
    { key: "status", label: "状态" },
    { key: "summary", label: "摘要" },
    { key: "created", label: "创建时间" },
  ];

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

  // 上传单个文件到指定目录
  async function uploadOne(file: File, folderId: string | null) {
    const form = new FormData();
    form.append("file", file);
    if (folderId) form.append("folder_id", folderId);
    await api.upload(`/workspaces/${workspaceId}/documents`, form);
  }

  // 目录上传：按 relativePath 逐级建子目录（缓存已建的路径→id），再上传文件
  async function ensureFolderPath(
    segments: string[],
    baseFolderId: string | null,
    cache: Map<string, string>
  ): Promise<string | null> {
    let parent = baseFolderId;
    let pathKey = "";
    for (const seg of segments) {
      pathKey += "/" + seg;
      const cached = cache.get(pathKey);
      if (cached) {
        parent = cached;
        continue;
      }
      const created = await api.post<Folder>(
        `/folders?workspace_id=${workspaceId}`,
        { name: seg, parent_id: parent }
      );
      cache.set(pathKey, created.id);
      parent = created.id;
    }
    return parent;
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0 || !workspaceId) return;
    setError(null);
    setUploading(true);
    const baseFolder =
      activeFolder !== ALL && activeFolder !== ROOT ? activeFolder : null;
    const pathCache = new Map<string, string>();
    try {
      for (const file of Array.from(files)) {
        // webkitRelativePath 形如 "顶层/子/文件.pdf"（目录上传时有值）
        const rel = (file as File & { webkitRelativePath?: string })
          .webkitRelativePath;
        let folderId = baseFolder;
        if (rel && rel.includes("/")) {
          // 规范化路径中每个目录名（去掉顶层目录名，保留子目录层级）
          const segs = rel.split("/").slice(0, -1).map(sanitizeName);
          folderId = await ensureFolderPath(segs, baseFolder, pathCache);
        }
        await uploadOne(file, folderId);
      }
      if (fileRef.current) fileRef.current.value = "";
      if (dirRef.current) dirRef.current.value = "";
      await loadFolders();
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

  async function previewDoc_(doc: DocumentPublic) {
    try {
      const token = getToken();
      const res = await fetch(`/api/documents/${doc.id}/preview`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setPreviewDoc(doc);
      setPreviewUrl(url);
    } catch {
      setError("预览失败");
    }
  }

  function closePreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewDoc(null);
    setPreviewUrl(null);
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
                  if (raw) { try { onDropItem(null, JSON.parse(raw)); } catch { /* ignore malformed drag payload */ } }
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
            <div className="mb-4 flex flex-wrap items-center gap-3 rounded border bg-white p-4">
              {/* 批量多文件 */}
              <input
                ref={fileRef}
                type="file"
                multiple
                onChange={(e) => handleFiles(e.target.files)}
                className="hidden"
              />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploading || !workspaceId}
                className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {uploading ? "上传中…" : "上传文件（可多选）"}
              </button>
              {/* 整目录上传（保持结构） */}
              <input
                ref={dirRef}
                type="file"
                // @ts-expect-error 非标准但主流浏览器支持：整目录选择
                webkitdirectory=""
                directory=""
                multiple
                onChange={(e) => handleFiles(e.target.files)}
                className="hidden"
              />
              <button
                onClick={() => dirRef.current?.click()}
                disabled={uploading || !workspaceId}
                className="rounded border border-blue-600 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
              >
                上传目录
              </button>
              {activeFolder !== ALL && activeFolder !== ROOT && (
                <span className="text-xs text-gray-400">
                  归入目录：{folderName(activeFolder)}
                </span>
              )}
            </div>
          )}

          {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

          {/* 隐藏的替换文件选择器 */}
          <input
            ref={replaceRef}
            type="file"
            className="hidden"
            onChange={onReplacePicked}
          />

          {/* 工具栏：搜索 + 自定义列 */}
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索标题/摘要/标签/分类…"
              className="w-64 rounded-full border px-4 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
            {tagFilter && (
              <span className="flex items-center gap-1 rounded-full bg-blue-100 px-3 py-0.5 text-xs text-blue-700">
                标签：{tagFilter}
                <button
                  onClick={() => setTagFilter(null)}
                  className="ml-0.5 font-bold hover:text-blue-900"
                  aria-label="清除标签过滤"
                >
                  ×
                </button>
              </span>
            )}
            <span className="text-xs text-gray-400">共 {shownDocs.length} 篇</span>
            <details className="relative ml-auto text-sm">
              <summary className="cursor-pointer rounded border px-3 py-1.5 text-gray-600 hover:bg-gray-100">
                展示列
              </summary>
              <div className="absolute right-0 z-10 mt-1 w-36 rounded border bg-white p-2 shadow-lg">
                {COLS.map((c) => (
                  <label key={c.key} className="flex items-center gap-2 px-1 py-1 text-xs">
                    <input
                      type="checkbox"
                      checked={cols[c.key]}
                      onChange={(e) =>
                        setCols((prev) => ({ ...prev, [c.key]: e.target.checked }))
                      }
                    />
                    {c.label}
                  </label>
                ))}
              </div>
            </details>
          </div>

          <div className="overflow-hidden rounded border bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-500">
                <tr>
                  <th className="px-4 py-2">标题</th>
                  {cols.folder && <th className="px-4 py-2">目录</th>}
                  {cols.category && <th className="px-4 py-2">分类</th>}
                  {cols.tags && <th className="px-4 py-2">标签</th>}
                  {cols.type && <th className="px-4 py-2">类型</th>}
                  {cols.status && <th className="px-4 py-2">状态</th>}
                  {cols.summary && <th className="px-4 py-2">摘要</th>}
                  {cols.created && <th className="px-4 py-2">创建时间</th>}
                  <th className="px-4 py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {shownDocs.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-6 text-center text-gray-400">
                      {docs.length === 0 ? "暂无文档" : "无匹配结果"}
                    </td>
                  </tr>
                )}
                {shownDocs.map((d) => (
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
                    {cols.folder && (
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
                          <span className="text-gray-500">
                            {folderName(d.folder_id)}
                          </span>
                        )}
                      </td>
                    )}
                    {cols.category && (
                      <td className="px-4 py-2 text-gray-600">
                        {categoryName(d.category_id)}
                      </td>
                    )}
                    {cols.tags && (
                      <td className="px-4 py-2">
                        <div className="flex flex-wrap gap-1">
                          {(d.tags ?? []).map((t) => (
                            <span
                              key={t}
                              onClick={() => setTagFilter(tagFilter === t ? null : t)}
                              className={`cursor-pointer rounded-full px-2 py-0.5 text-xs transition-colors ${
                                tagFilter === t
                                  ? "bg-blue-200 text-blue-800"
                                  : "bg-gray-100 text-gray-600 hover:bg-blue-100 hover:text-blue-700"
                              }`}
                              title="点击过滤该标签"
                            >
                              {t}
                            </span>
                          ))}
                          {(!d.tags || d.tags.length === 0) && (
                            <span className="text-gray-400">—</span>
                          )}
                        </div>
                      </td>
                    )}
                    {cols.type && (
                      <td className="px-4 py-2 text-xs text-gray-500">
                        {d.mime_type}
                      </td>
                    )}
                    {cols.status && (
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
                    )}
                    {cols.summary && (
                      <td className="max-w-xs px-4 py-2 text-gray-600">
                        <div className="group relative">
                          <span className="line-clamp-2 cursor-help">
                            {d.brief || d.summary || "—"}
                          </span>
                          {(d.brief || d.summary) && (
                            <div className="pointer-events-none absolute left-0 top-full z-20 mt-1 hidden w-80 rounded-lg border border-gray-200 bg-white p-3 text-xs leading-relaxed text-gray-700 shadow-lg group-hover:block">
                              {d.summary || d.brief}
                            </div>
                          )}
                        </div>
                      </td>
                    )}
                    {cols.created && (
                      <td className="whitespace-nowrap px-4 py-2 text-xs text-gray-500">
                        {new Date(d.created_at).toLocaleString()}
                      </td>
                    )}
                    <td className="whitespace-nowrap px-4 py-2">
                      <button
                        onClick={() => previewDoc_(d)}
                        className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                      >
                        预览
                      </button>
                      <button
                        onClick={() => download(d)}
                        className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-blue-700 hover:bg-gray-200"
                      >
                        下载
                      </button>
                      <button
                        onClick={() => setDetailDoc(d)}
                        className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                      >
                        文件详情
                      </button>
                      <button
                        onClick={() => setLogDoc(d)}
                        className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                      >
                        处理详情
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

      {detailDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setDetailDoc(null)}>
          <div className="w-full max-w-6xl rounded-xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b px-5 py-4">
              <h2 className="flex-1 truncate pr-4 text-sm font-semibold text-gray-800">{detailDoc.title}</h2>
              <button onClick={() => setDetailDoc(null)} className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="max-h-[85vh] overflow-y-auto p-5">
              <table className="w-full text-sm">
                <tbody className="divide-y divide-gray-100">
                  <tr className="align-top">
                    <td className="w-24 shrink-0 py-3 pr-4 font-medium text-gray-500">分类</td>
                    <td className="py-3 text-gray-800">{categoryName(detailDoc.category_id)}</td>
                  </tr>
                  <tr className="align-top">
                    <td className="py-3 pr-4 font-medium text-gray-500">简介</td>
                    <td className="py-3 text-gray-800 leading-relaxed">{detailDoc.brief || "—"}</td>
                  </tr>
                  <tr className="align-top">
                    <td className="py-3 pr-4 font-medium text-gray-500">摘要</td>
                    <td className="py-3 text-gray-800 leading-relaxed whitespace-pre-wrap">{detailDoc.summary || "—"}</td>
                  </tr>
                  <tr className="align-top">
                    <td className="py-3 pr-4 font-medium text-gray-500">标签</td>
                    <td className="py-3">
                      {detailDoc.tags && detailDoc.tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {detailDoc.tags.map((t) => (
                            <span key={t} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{t}</span>
                          ))}
                        </div>
                      ) : "—"}
                    </td>
                  </tr>
                  <tr className="align-top">
                    <td className="py-3 pr-4 font-medium text-gray-500">正文全文</td>
                    <td className="py-3">
                      {detailDoc.content_text ? (
                        <div className="max-h-[55vh] overflow-y-auto rounded border border-gray-200 bg-gray-50 p-3 text-xs leading-relaxed">
                          <Markdown content={detailDoc.content_text} />
                        </div>
                      ) : "—"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {logDoc && (
        <TaskLogPanel
          documentId={logDoc.id}
          title={logDoc.title}
          onClose={() => setLogDoc(null)}
        />
      )}

      {previewDoc && previewUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="flex w-full max-w-4xl flex-col rounded-lg bg-white shadow-2xl" style={{ height: "85vh" }}>
            <div className="flex items-center justify-between border-b px-4 py-3">
              <span className="max-w-lg truncate text-sm font-medium text-gray-800">
                {previewDoc.title}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => download(previewDoc)}
                  className="rounded bg-gray-100 px-3 py-1.5 text-xs text-blue-700 hover:bg-gray-200"
                >
                  下载
                </button>
                <button
                  onClick={closePreview}
                  className="rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-200"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              {previewDoc.mime_type?.startsWith("image/") ? (
                <div className="flex h-full items-center justify-center overflow-auto p-4">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={previewUrl} alt={previewDoc.title} className="max-h-full max-w-full object-contain" />
                </div>
              ) : previewDoc.mime_type === "application/pdf" ? (
                <iframe
                  src={previewUrl}
                  className="h-full w-full border-0"
                  title={previewDoc.title}
                  sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
                />
              ) : (
                <iframe
                  src={previewUrl}
                  className="h-full w-full border-0"
                  title={previewDoc.title}
                  sandbox="allow-same-origin"
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
