"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import Markdown from "@/components/Markdown";
import type { AgentRun, SourceRef } from "@/lib/types";

interface Props {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  agentRuns?: AgentRun[];
  errorKey?: string;
  warning?: string;
  onDownload?: (s: SourceRef) => void;
  onEdit?: (newContent: string) => void;
  onResend?: () => void;
}

export default function MessageBubble({ role, content, sources, agentRuns, errorKey, warning, onDownload, onEdit, onResend }: Props) {
  const t = useTranslations("messageBubble");
  const isUser = role === "user";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const [copied, setCopied] = useState(false);
  const [selectedSource, setSelectedSource] = useState<{ id: string } | null>(null);
  const selected = sources?.find((s) => s.citation_id === selectedSource?.id);
  const evidenceId = useId();
  const evidenceRef = useRef<HTMLDivElement>(null);
  const excerptRef = useRef<HTMLQuoteElement>(null);

  useEffect(() => {
    const panel = evidenceRef.current;
    if (!selectedSource || !panel) return;
    if (excerptRef.current) excerptRef.current.scrollTop = 0;
    panel.focus({ preventScroll: true });
    panel.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
      block: "start",
    });
  }, [selectedSource]);

  function openSource(id: string) {
    // A new selection also scrolls when the same citation is clicked again.
    setSelectedSource({ id });
  }
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function sourceLabel(source: SourceRef) {
    if (source.source_type === "paloalto_kb") return `Palo Alto KB · ${t("source_paloalto_kb")}`;
    if (source.source_type === "paloalto_live") return `LIVEcommunity · ${t("source_paloalto_live")}`;
    if (source.source_type === "paloalto_docs") return `Palo Alto Docs · ${t("source_paloalto_docs")}`;
    return source.workspace_name ?? source.source_type ?? "";
  }

  function copyContent() {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

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
          <div className={`relative ${isUser ? "pb-6" : ""}`}>
            <div
              className={`rounded-2xl py-3 pl-4 text-sm leading-relaxed ${
                isUser
                  ? "rounded-tr-sm bg-blue-600 pr-4 text-white whitespace-pre-wrap"
                  : "rounded-tl-sm border border-gray-200 bg-white pr-10 text-gray-700 shadow-sm"
              }`}
            >
              {isUser
                ? content
                : errorKey
                  ? <span className="text-red-500">{t(errorKey as Parameters<typeof t>[0])}</span>
                  : <Markdown content={content}
                      citationIds={sources?.flatMap((s) => s.citation_id ? [s.citation_id] : [])}
                      onCitationClick={openSource}
                      citationTargetId={evidenceId} activeCitationId={selectedSource?.id} />
              }
            </div>
            {/* 右下角操作按钮 */}
            <div
              className={`absolute flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 ${
                isUser ? "bottom-0 right-0" : "bottom-1 right-1"
              }`}
            >
              {isUser && onEdit && (
                <button
                  onClick={startEdit}
                  title={t("edit_resend")}
                  className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
              )}
              <button
                onClick={copyContent}
                title={t("copy")}
                className={`rounded p-1 hover:bg-gray-100 ${copied ? "text-green-500" : "text-gray-500 hover:text-gray-700"}`}
              >
                {copied ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                  </svg>
                )}
              </button>
            </div>
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
                key={s.id ?? s.doc_id ?? s.url}
                onClick={() => s.citation_id
                  ? setSelectedSource(selectedSource?.id === s.citation_id ? null : { id: s.citation_id })
                  : onDownload?.(s)}
                className="flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-xs text-blue-600 hover:border-blue-300 hover:bg-blue-50 transition-colors"
                aria-expanded={s.citation_id ? selectedSource?.id === s.citation_id : undefined}
                aria-controls={s.citation_id ? evidenceId : undefined}
                title={s.citation_id ? t("view_evidence") : t("download_original")}
              >
                <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M9 2H4a1 1 0 00-1 1v10a1 1 0 001 1h8a1 1 0 001-1V6l-4-4zm1 4V3l3 3h-3z"/>
                </svg>
                {s.citation_id && `[${s.citation_id}] `}
                {sourceLabel(s) ? `${sourceLabel(s)} · ` : ""}{s.title}
              </button>
            ))}
          </div>
        )}
        {!isUser && warning && (
          <p role="status" className="text-xs text-amber-700">
            {t(warning as Parameters<typeof t>[0])}
          </p>
        )}
        {agentRuns && agentRuns.length > 0 && (
          <details className="text-xs text-gray-500">
            <summary className="cursor-pointer">{t("retrieval_scope")}</summary>
            <ul className="mt-1 space-y-1">
              {agentRuns.map((run) => <li key={run.agent_id}>
                {run.name} · {run.status === "failed" ? t("agent_failed")
                  : t("evidence_count", { count: run.evidence_count ?? 0 })}
                {run.status === "done" && run.indexed_count !== undefined
                  && ` · ${t(run.source_type?.startsWith("paloalto_") ? "candidate_count" : "indexed_count", { count: run.indexed_count })}`}
                {run.truncated && ` · ${t(run.source_type?.startsWith("paloalto_") ? "more_search_results" : "index_truncated")}`}
              </li>)}
            </ul>
          </details>
        )}
        {selected && (
          <div ref={evidenceRef} id={evidenceId} role="region" tabIndex={-1}
            aria-label={`[${selected.citation_id}] ${selected.title}`}
            className="w-full scroll-mt-4 rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-300">
            <div className="font-medium">[{selected.citation_id}] {selected.title}</div>
            <div className="mt-1 text-gray-500">
              {sourceLabel(selected)}
              {selected.version && ` · ${selected.version}`}
              {selected.content_kind === "processed_text" && ` · ${t("processed_text")}`}
              {selected.content_kind === "summary" && ` · ${t("summary")}`}
              {selected.content_kind === "document_metadata" && ` · ${t("document_metadata")}`}
              {selected.content_kind === "document_catalog" && ` · ${t("document_catalog")}`}
              {selected.content_kind === "indexed_web_page" && ` · ${t("indexed_web_page")}`}
              {selected.content_kind === "external_excerpt" && ` · ${t("external_excerpt")}`}
              {selected.content_kind === "web_page" && ` · ${t("web_page")}`}
            </div>
            {selected.product && <div className="mt-1">{selected.product}</div>}
            {(["updated_at", "indexed_at", "retrieved_at"] as const).map((field) => selected[field] && (
              <div key={field} className="mt-1 text-gray-500">{t(field)}: {selected[field]}</div>
            ))}
            {selected.excerpt && <blockquote ref={excerptRef} className="my-2 max-h-60 overflow-y-auto whitespace-pre-wrap border-l-2 border-blue-200 pl-3">{selected.excerpt}</blockquote>}
            {selected.doc_id && <button type="button" onClick={() => onDownload?.(selected)}
              className="text-blue-600 underline">{t("download_original")}</button>}
            {selected.url && /^https?:\/\//i.test(selected.url) && (
              <a href={selected.url} target="_blank" rel="noopener noreferrer"
                className="text-blue-600 underline">{t("open_source")}</a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
