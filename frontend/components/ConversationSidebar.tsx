"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { useDialog } from "@/components/DialogProvider";
import type { ConversationSummary } from "@/lib/types";

interface Props {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onUpdated?: (conv: ConversationSummary) => void;
  onDeleted?: (id: string) => void;
}

export default function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onUpdated,
  onDeleted,
}: Props) {
  const t = useTranslations("sidebar");
  const { showConfirm } = useDialog();
  const [collapsed, setCollapsed] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const editRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingId) editRef.current?.focus();
  }, [editingId]);

  function startEdit(conv: ConversationSummary, e: React.MouseEvent) {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditValue(conv.title ?? "");
  }

  async function commitEdit(conv: ConversationSummary) {
    const title = editValue.trim();
    setEditingId(null);
    if (!title || title === conv.title) return;
    try {
      const updated = await api.patch<ConversationSummary>(
        `/conversations/${conv.id}`,
        { title }
      );
      onUpdated?.(updated);
    } catch {
      // 失败静默，下次刷新恢复
    }
  }

  async function togglePin(conv: ConversationSummary, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      const updated = await api.patch<ConversationSummary>(
        `/conversations/${conv.id}`,
        { pinned: !conv.pinned }
      );
      onUpdated?.(updated);
    } catch {
      // 失败静默
    }
  }

  async function deleteConv(conv: ConversationSummary, e: React.MouseEvent) {
    e.stopPropagation();
    const ok = await showConfirm(t("delete_confirm", { title: conv.title ?? t("untitled") }));
    if (!ok) return;
    try {
      await api.del(`/conversations/${conv.id}`);
      onDeleted?.(conv.id);
    } catch {
      // 失败静默
    }
  }

  if (collapsed) {
    return (
      <aside className="flex w-10 shrink-0 flex-col items-center border-r border-gray-200 bg-white py-2">
        <button
          onClick={() => setCollapsed(false)}
          title={t("expand")}
          className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center gap-2 p-3">
        <button
          onClick={onNew}
          className="flex-1 rounded-lg bg-blue-600 py-2 px-3 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          {t("new_conversation")}
        </button>
        <button
          onClick={() => setCollapsed(true)}
          title={t("collapse")}
          className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {conversations.length === 0 && (
          <p className="px-3 py-4 text-center text-xs text-gray-400">{t("no_conversations")}</p>
        )}
        {conversations.map((c) => (
          <div
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={`group relative flex w-full cursor-pointer items-start rounded-lg px-3 py-2.5 transition-colors ${
              c.id === activeId
                ? "bg-blue-50 text-blue-700"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            {/* Pin indicator */}
            {c.pinned && (
              <span className="mr-1.5 mt-0.5 shrink-0 text-blue-400" title={t("pinned_title")}>
                <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/>
                </svg>
              </span>
            )}

            <div className="min-w-0 flex-1">
              {editingId === c.id ? (
                <input
                  ref={editRef}
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={() => commitEdit(c)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitEdit(c);
                    if (e.key === "Escape") setEditingId(null);
                    e.stopPropagation();
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="w-full rounded border border-blue-400 px-1 py-0 text-sm text-gray-900 outline-none"
                  maxLength={100}
                />
              ) : (
                <span
                  className="block truncate text-sm font-medium"
                  title={c.title ?? undefined}
                  onDoubleClick={(e) => startEdit(c, e)}
                >
                  {c.title ?? t("untitled")}
                </span>
              )}
              <span className="mt-0.5 block text-xs text-gray-400">
                {new Date(c.created_at).toLocaleDateString()}
              </span>
            </div>

            {/* Action buttons — shown on hover */}
            {editingId !== c.id && (
              <div className="ml-1 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  onClick={(e) => togglePin(c, e)}
                  title={c.pinned ? t("unpin") : t("pin")}
                  className={`rounded p-0.5 hover:bg-gray-200 ${c.pinned ? "text-blue-500" : "text-gray-400"}`}
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/>
                  </svg>
                </button>
                <button
                  onClick={(e) => startEdit(c, e)}
                  title={t("rename")}
                  className="rounded p-0.5 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  onClick={(e) => deleteConv(c, e)}
                  title={t("delete")}
                  className="rounded p-0.5 text-gray-400 hover:bg-red-100 hover:text-red-500"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
