"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import NavBar from "@/components/NavBar";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken, isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type { DocumentPublic } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  processing: "归类中",
  ready: "已就绪",
  failed: "失败",
};

export default function DocumentsPage() {
  const ready = useAuthGuard();
  const admin = isAdmin();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [docs, setDocs] = useState<DocumentPublic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const list = await api.get<DocumentPublic[]>(
        `/workspaces/${workspaceId}/documents`
      );
      setDocs(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  // 有 processing 文档时轮询刷新状态
  useEffect(() => {
    if (!docs.some((d) => d.status === "processing")) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [docs, load]);

  if (!ready) return null;

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !workspaceId) return;
    setError(null);
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await api.upload(`/workspaces/${workspaceId}/documents`, form);
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setUploading(false);
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
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <div className="flex items-center gap-3 border-b bg-white px-4 py-2">
        <span className="text-sm text-gray-500">空间：</span>
        <WorkspacePicker value={workspaceId} onChange={setWorkspaceId} />
      </div>

      <main className="mx-auto w-full max-w-4xl flex-1 p-4">
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
          </form>
        )}

        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

        <div className="overflow-hidden rounded border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-500">
              <tr>
                <th className="px-4 py-2">标题</th>
                <th className="px-4 py-2">状态</th>
                <th className="px-4 py-2">摘要</th>
                <th className="px-4 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {docs.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-gray-400">
                    暂无文档
                  </td>
                </tr>
              )}
              {docs.map((d) => (
                <tr key={d.id} className="border-t">
                  <td className="px-4 py-2">{d.title}</td>
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
                  {/* 摘要为 LLM 产物，纯文本渲染避免 XSS */}
                  <td className="max-w-xs truncate px-4 py-2 text-gray-600">
                    {d.summary ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => download(d)}
                      className="rounded bg-gray-100 px-2 py-1 text-xs text-blue-700 hover:bg-gray-200"
                    >
                      下载
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
