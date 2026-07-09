"use client";

import Markdown from "@/components/Markdown";
import type { SourceRef } from "@/lib/types";

interface Props {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  onDownload?: (s: SourceRef) => void;
}

export default function MessageBubble({ role, content, sources, onDownload }: Props) {
  const isUser = role === "user";
  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white text-gray-700 border border-gray-200 shadow-sm"
        }`}
        aria-hidden
      >
        {isUser ? "我" : "AI"}
      </div>

      <div className={`flex max-w-[75%] flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "rounded-tr-sm bg-blue-600 text-white whitespace-pre-wrap"
              : "rounded-tl-sm bg-white text-gray-900 border border-gray-200 shadow-sm"
          }`}
        >
          {isUser ? content : <Markdown content={content} />}
        </div>

        {sources && sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {sources.map((s) => (
              <button
                key={s.doc_id}
                onClick={() => onDownload?.(s)}
                className="flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-xs text-blue-600 hover:border-blue-300 hover:bg-blue-50 transition-colors"
                title="下载原文"
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
