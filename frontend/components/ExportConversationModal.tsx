"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import FolderTree, { buildTree } from "@/components/FolderTree";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Folder, Workspace } from "@/lib/types";
import type { ConversationHistory } from "@/lib/types";

interface Props {
  conversationId: string;
  conversationTitle: string | null;
  onClose: () => void;
}

type Format = "docx" | "md" | "pdf";

const NO_OP = () => {};

export default function ExportConversationModal({ conversationId, conversationTitle, onClose }: Props) {
  const t = useTranslations("chat");

  const [messages, setMessages] = useState<ConversationHistory["messages"]>([]);
  const [loading, setLoading] = useState(true);

  // 以「问答对」为单位：每个用户消息对应一个 checkbox
  // selectedPairs[i] = true 表示第 i 个用户消息及其紧随的 AI 回复均选中
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const [format, setFormat] = useState<Format>("docx");

  // 下载状态
  const [downloading, setDownloading] = useState(false);

  // 存入库状态
  const [saveOpen, setSaveOpen] = useState(false);
  const [wsId, setWsId] = useState<string | null>(null);
  const [wsRole, setWsRole] = useState<string | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // 加载消息列表
  useEffect(() => {
    setLoading(true);
    api.get<ConversationHistory>(`/conversations/${conversationId}`)
      .then((hist) => {
        setMessages(hist.messages);
        setSelectedIds(new Set(hist.messages.map((m) => m.id)));
      })
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  }, [conversationId]);

  const allSelected = messages.length > 0 && messages.every((m) => selectedIds.has(m.id));

  function toggleAll() {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(messages.map((m) => m.id)));
    }
  }

  function toggleMessage(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // 下载
  async function handleDownload() {
    if (selectedIds.size === 0) return;
    setDownloading(true);
    try {
      const token = getToken();
      const res = await fetch(`/api/conversations/${conversationId}/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          format,
          message_ids: Array.from(selectedIds),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") ?? "";
      const match = cd.match(/filename\*?=(?:UTF-8'')?([^;\r\n]+)/i);
      const filename = match
        ? decodeURIComponent(match[1].replace(/"/g, ""))
        : `conversation.${format}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // 静默失败；实际错误少见
    } finally {
      setDownloading(false);
    }
  }

  // 存入库：空间切换
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

  async function handleSaveToLib() {
    if (!wsId || selectedIds.size === 0) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      await api.post(`/conversations/${conversationId}/export-to-library`, {
        format,
        message_ids: Array.from(selectedIds),
        workspace_id: wsId,
        folder_id: folderId,
      });
      setSaved(true);
    } catch (e) {
      setSaveMsg(e instanceof ApiError ? e.message : t("exportModal_saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl bg-white shadow-2xl">
        {/* 标题栏 */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">{t("exportModal_title")}</h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* 格式选择 */}
          <div>
            <p className="mb-2 text-xs font-medium text-gray-500 uppercase tracking-wide">格式</p>
            <div className="flex gap-3">
              {(["docx", "md", "pdf"] as Format[]).map((f) => (
                <label
                  key={f}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2.5 text-sm transition-colors ${
                    format === f
                      ? "border-blue-500 bg-blue-50 text-blue-700"
                      : "border-gray-200 text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <input
                    type="radio"
                    name="format"
                    value={f}
                    checked={format === f}
                    onChange={() => setFormat(f)}
                    className="sr-only"
                  />
                  {f === "docx" ? (
                    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM8.5 18l-2-6h1.3l1.2 4.1 1.3-4.1h1.2l1.3 4.1 1.2-4.1H15l-2 6h-1.2l-1.3-4.1L9.7 18H8.5z"/>
                    </svg>
                  ) : f === "pdf" ? (
                    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM7 16.5c0 .28-.22.5-.5.5H6v1H5v-4h1.5c.83 0 1.5.67 1.5 1.5v1zm4.5.5H10v1H9v-4h2.5c.28 0 .5.22.5.5v2c0 .28-.22.5-.5.5zm4-2.5h-2v1h1.5v1H13.5v1H13v-4h2.5v1z"/>
                      <path d="M6 15h.5v1H6v-1zm4 0h.5v1H10v-1z"/>
                    </svg>
                  ) : (
                    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  )}
                  {f === "docx" ? t("exportModal_format_docx") : f === "pdf" ? t("exportModal_format_pdf") : t("exportModal_format_md")}
                </label>
              ))}
            </div>
          </div>

          {/* 消息选择 */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{t("exportModal_selectMessages")}</p>
              <button
                onClick={toggleAll}
                className="text-xs text-blue-600 hover:underline"
              >
                {allSelected ? t("exportModal_deselectAll") : t("exportModal_selectAll")}
              </button>
            </div>
            {loading ? (
              <p className="py-4 text-center text-sm text-gray-400">{t("exportModal_loading")}</p>
            ) : (
              <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-xl border border-gray-100 bg-gray-50 p-2">
                {messages.map((msg) => (
                  <label
                    key={msg.id}
                    className={`flex cursor-pointer items-start gap-2.5 rounded-lg px-3 py-2 transition-colors ${
                      selectedIds.has(msg.id) ? "bg-white shadow-sm" : "opacity-50 hover:opacity-70"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.has(msg.id)}
                      onChange={() => toggleMessage(msg.id)}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded accent-blue-600"
                    />
                    <div className="min-w-0 flex-1">
                      <span
                        className={`mr-2 inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
                          msg.role === "user"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {msg.role === "user" ? "Q" : "A"}
                      </span>
                      <span className="text-xs text-gray-600 line-clamp-1">{msg.content.slice(0, 80)}</span>
                    </div>
                  </label>
                ))}
              </div>
            )}
            {selectedIds.size === 0 && !loading && (
              <p className="mt-1 text-xs text-amber-600">{t("exportModal_noMessages")}</p>
            )}
          </div>

          {/* 存入库面板 */}
          <div className="rounded-xl border border-gray-200">
            <button
              type="button"
              onClick={() => setSaveOpen((o) => !o)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 rounded-xl transition-colors"
            >
              <span className="flex items-center gap-2">
                <svg className="h-4 w-4 text-emerald-600" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M3 5a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2V5z" />
                </svg>
                {t("exportModal_saveToLib")}
              </span>
              <svg
                className={`h-4 w-4 text-gray-400 transition-transform ${saveOpen ? "rotate-180" : ""}`}
                viewBox="0 0 20 20" fill="currentColor"
              >
                <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>

            {saveOpen && (
              <div className="border-t border-gray-100 px-4 py-3 space-y-3">
                {saved ? (
                  <p className="py-2 text-center text-sm text-green-600">{t("exportModal_saved")}</p>
                ) : (
                  <>
                    <div>
                      <p className="mb-1.5 text-xs text-gray-500">{t("exportModal_workspace")}</p>
                      <WorkspacePicker
                        value={wsId}
                        onChange={handleWsChange}
                        onWorkspaceChange={onWorkspaceChange}
                      />
                    </div>

                    {wsId !== null && !canSaveHere && (
                      <p className="text-xs text-amber-600">{t("exportModal_noPermission")}</p>
                    )}

                    {canSaveHere && (
                      <div>
                        <p className="mb-1.5 text-xs text-gray-500">{t("exportModal_folder")}</p>
                        <div className="max-h-36 overflow-y-auto rounded-lg border border-gray-200 p-1">
                          <button
                            type="button"
                            onClick={() => setFolderId(null)}
                            className={`w-full rounded px-2 py-1 text-left text-xs ${
                              folderId === null ? "bg-emerald-50 text-emerald-700" : "text-gray-600 hover:bg-gray-50"
                            }`}
                          >
                            根目录
                          </button>
                          {loadingFolders ? (
                            <p className="px-2 py-1 text-xs text-gray-400">{t("exportModal_saving")}</p>
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

                    {saveMsg && <p className="text-xs text-red-500">{saveMsg}</p>}

                    <button
                      type="button"
                      onClick={handleSaveToLib}
                      disabled={saving || !canSaveHere || selectedIds.size === 0}
                      className="w-full rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40 transition-colors"
                    >
                      {saving ? t("exportModal_saving") : t("exportModal_confirm")}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* 底部操作栏 */}
        <div className="flex items-center justify-end gap-3 border-t border-gray-100 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
          >
            关闭
          </button>
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading || selectedIds.size === 0}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
            {downloading ? "…" : t("exportModal_download")}
          </button>
        </div>
      </div>
    </div>
  );
}
