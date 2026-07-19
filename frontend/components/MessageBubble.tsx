"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import Markdown from "@/components/Markdown";
import type { SourceRef } from "@/lib/types";

interface Props {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  errorKey?: string;
  onDownload?: (s: SourceRef) => void;
  onEdit?: (newContent: string) => void;
  onResend?: () => void;
}

export default function MessageBubble({ role, content, sources, errorKey, onDownload, onEdit, onResend }: Props) {
  const t = useTranslations("messageBubble");
  const isUser = role === "user";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function startEdit() {
    setDraft(content);
    setEditing(true);
    setTimeout(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      el.selectionStart = el.value.length;
    }, 0);
  }

  function cancelEdit() {
    setEditing(false);
    setDraft(content);
  }

  function commitEdit() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== content) {
      onEdit?.(trimmed);
    }
    setEditing(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      commitEdit();
    }
    if (e.key === "Escape") cancelEdit();
  }

  return (
    <div className={`group flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white text-gray-700 border border-gray-200 shadow-sm"
        }`}
        aria-hidden
      >
        {isUser ? t("me") : "AI"}
      </div>

      <div className={`flex max-w-[75%] flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
        {isUser && editing ? (
          <div className="w-full min-w-[240px]">
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={3}
              className="w-full rounded-2xl rounded-tr-sm border border-blue-400 bg-blue-50 px-4 py-3 text-sm text-gray-900 outline-none resize-none"
            />
            <div className="mt-1 flex justify-end gap-2">
              <button onClick={cancelEdit} className="rounded px-3 py-1 text-xs text-gray-500 hover:bg-gray-100">
                {t("cancel")}
              </button>
              <button
                onClick={commitEdit}
                disabled={!draft.trim()}
                className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {t("resend")}
              </button>
            </div>
          </div>
        ) : (
          <div className="relative">
            <div
              className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                isUser
                  ? "rounded-tr-sm bg-blue-600 text-white whitespace-pre-wrap"
                  : "rounded-tl-sm bg-white text-gray-700 border border-gray-200 shadow-sm"
              }`}
            >
              {isUser
                ? content
                : errorKey
                  ? <span className="text-red-500">{t(errorKey as Parameters<typeof t>[0])}</span>
                  : <Markdown content={content} />
              }
            </div>
            {isUser && onEdit && (
              <button
                onClick={startEdit}
                title={t("edit_resend")}
                className="absolute -left-7 top-1/2 -translate-y-1/2 rounded p-1 text-gray-300 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-gray-100 hover:text-gray-500"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
            )}
          </div>
        )}

        {isUser && onResend && (
          <button
            onClick={onResend}
            className="flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs text-amber-700 hover:bg-amber-100 transition-colors"
          >
            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
            {t("resend")}
          </button>
        )}

        {sources && sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {sources.map((s) => (
              <button
                key={s.doc_id}
                onClick={() => onDownload?.(s)}
                className="flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-xs text-blue-600 hover:border-blue-300 hover:bg-blue-50 transition-colors"
                title={t("download_original")}
              >
                <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M9 2H4a1 1 0 00-1 1v10a1 1 0 001 1h8a1 1 0 001-1V6l-4-4zm1 4V3l3 3h-3z"/>
                </svg>
                {s.title}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
