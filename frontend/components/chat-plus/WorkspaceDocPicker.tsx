"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";

interface Doc {
  id: string;
  title: string;
  status: string;
}

interface Props {
  workspaceId: string | null;
  onWorkspaceChange: (id: string | null) => void;
  docIds: string[];
  onDocsChange: (ids: string[]) => void;
  allDocs: boolean;
  onAllDocsChange: (v: boolean) => void;
  useOriginal: boolean;
  onUseOriginalChange: (v: boolean) => void;
}

const PAGE_SIZE = 50;
// 与后端 MAX_PLUS_CONTEXT_DOCS 对齐：超过则仅前 N 篇正文被引用
const MAX_CONTEXT_DOCS = 20;

/**
 * 聊天+ 底部工具条的「工作区 + 文档」选择器。
 * - 工作区作为可选项收进工具条；
 * - 文档：服务端搜索 + 翻页（加载更多）+「所有文件」开关；
 * - 不勾选任何文档且未开「所有文件」= 纯对话。
 */
export default function WorkspaceDocPicker({
  workspaceId,
  onWorkspaceChange,
  docIds,
  onDocsChange,
  allDocs,
  onAllDocsChange,
  useOriginal,
  onUseOriginalChange,
}: Props) {
  const t = useTranslations("chatComponents");
  const [open, setOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<Workspace[]>("/workspaces").then(setWorkspaces).catch(() => setWorkspaces([]));
  }, []);

  const fetchDocs = useCallback(
    async (ws: string, q: string, pageNum: number, append: boolean) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          size: String(PAGE_SIZE),
          page: String(pageNum),
        });
        if (q.trim()) params.set("search", q.trim());
        const r = await api.get<Doc[]>(`/workspaces/${ws}/documents?${params}`);
        const ready = r.filter((d) => d.status === "ready");
        setHasMore(r.length === PAGE_SIZE);
        setDocs((prev) => (append ? [...prev, ...ready] : ready));
      } catch {
        if (!append) setDocs([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // workspace 或搜索变化：重置到第 1 页（搜索 debounce）
  useEffect(() => {
    if (!workspaceId) {
      setDocs([]);
      return;
    }
    const t = setTimeout(() => {
      setPage(1);
      fetchDocs(workspaceId, search, 1, false);
    }, 250);
    return () => clearTimeout(t);
  }, [workspaceId, search, fetchDocs]);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function loadMore() {
    if (!workspaceId || loading) return;
    const next = page + 1;
    setPage(next);
    fetchDocs(workspaceId, search, next, true);
  }

  function toggleDoc(id: string) {
    if (docIds.includes(id)) onDocsChange(docIds.filter((d) => d !== id));
    else onDocsChange([...docIds, id]);
  }

  const currentWs = workspaces.find((w) => w.id === workspaceId);
  const wsName = currentWs?.name ?? t("workspace");
  const label = !workspaceId
    ? t("refWorkspaceOptional")
    : allDocs
    ? `${wsName} · ${t("allFiles")}`
    : docIds.length > 0
    ? `${wsName} · ${t("docsCount", { count: docIds.length })}`
    : wsName;

  const overLimit = allDocs || docIds.length > MAX_CONTEXT_DOCS;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
          workspaceId
            ? "border-purple-300 bg-purple-50 text-purple-700"
            : "border-gray-300 bg-white text-gray-600 hover:border-purple-400 hover:text-purple-600"
        }`}
        title={t("wsPickerHint")}
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
          <path d="M2 5a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V5z" />
        </svg>
        {label}
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-1 w-80 rounded-lg border border-gray-200 bg-white shadow-xl">
          {/* 工作区选择 */}
          <div className="border-b border-gray-100 p-2">
            <p className="mb-1 px-1 text-xs text-gray-400">{t("wsPickerHint")}</p>
            <select
              value={workspaceId ?? ""}
              onChange={(e) => {
                onWorkspaceChange(e.target.value || null);
                onDocsChange([]);
                onAllDocsChange(false);
              }}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs text-gray-800 outline-none focus:border-purple-400"
            >
              <option value="">{t("noWorkspace")}</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>

          {/* 文档子菜单（选中工作区后展示）*/}
          {workspaceId && (
            <>
              {/* 所有文件开关 */}
              <label className="flex cursor-pointer items-center gap-2 border-b border-gray-100 px-3 py-2 hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={allDocs}
                  onChange={(e) => {
                    onAllDocsChange(e.target.checked);
                    if (e.target.checked) onDocsChange([]);
                  }}
                  className="h-3.5 w-3.5 shrink-0"
                />
                <span className="text-xs font-medium text-gray-700">{t("allFiles")}</span>
                <span className="text-xs text-gray-400">{t("allFilesHint")}</span>
              </label>

              {/* 读取原始文件开关：把原文件拷进工作目录供 Claude 读全文（仅有选择时可用）*/}
              {(allDocs || docIds.length > 0) && (
                <label className="flex cursor-pointer items-center gap-2 border-b border-gray-100 px-3 py-2 hover:bg-gray-50">
                  <input
                    type="checkbox"
                    checked={useOriginal}
                    onChange={(e) => onUseOriginalChange(e.target.checked)}
                    className="h-3.5 w-3.5 shrink-0"
                  />
                  <span className="text-xs font-medium text-gray-700">{t("useOriginal")}</span>
                  <span className="text-xs text-gray-400">{t("useOriginalHint")}</span>
                </label>
              )}

              {/* 上下文限量提示 */}
              {overLimit && (
                <p className="border-b border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  {t("overLimitHint", { max: MAX_CONTEXT_DOCS })}
                </p>
              )}

              {!allDocs && (
                <>
                  <div className="p-2">
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder={t("searchDocs")}
                      className="w-full rounded border border-gray-200 px-2 py-1 text-xs outline-none focus:border-purple-400"
                    />
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {docs.length === 0 ? (
                      <p className="px-4 py-3 text-xs text-gray-400">
                        {loading ? t("loading") : t("noReadyDocs")}
                      </p>
                    ) : (
                      <>
                        {docs.map((d) => (
                          <label
                            key={d.id}
                            className="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-gray-50"
                          >
                            <input
                              type="checkbox"
                              checked={docIds.includes(d.id)}
                              onChange={() => toggleDoc(d.id)}
                              className="h-3.5 w-3.5 shrink-0"
                            />
                            <span className="truncate text-xs text-gray-700">{d.title}</span>
                          </label>
                        ))}
                        {hasMore && (
                          <button
                            type="button"
                            onClick={loadMore}
                            disabled={loading}
                            className="w-full px-3 py-2 text-center text-xs text-purple-600 hover:bg-purple-50 disabled:opacity-40"
                          >
                            {loading ? t("loading") : t("loadMore")}
                          </button>
                        )}
                      </>
                    )}
                  </div>
                  {docIds.length > 0 && (
                    <div className="border-t border-gray-100 px-3 py-1.5">
                      <button
                        type="button"
                        onClick={() => onDocsChange([])}
                        className="text-xs text-gray-400 hover:text-gray-600"
                      >
                        {t("clearDocs")}
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
