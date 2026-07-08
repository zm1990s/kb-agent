"use client";

import Markdown from "@/components/Markdown";
import type { SourceRef } from "@/lib/types";

interface Props {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  onDownload?: (s: SourceRef) => void;
}

// 气泡式消息：用户靠右蓝底，助手靠左白底带头像；助手内容 Markdown 渲染。
export default function MessageBubble({ role, content, sources, onDownload }: Props) {
  const isUser = role === "user";
  return (
    <div className={`flex gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
          isUser ? "bg-blue-600 text-white" : "bg-emerald-500 text-white"
        }`}
        aria-hidden
      >
        {isUser ? "我" : "AI"}
      </div>
      <div className={`flex max-w-[80%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "whitespace-pre-wrap rounded-tr-sm bg-blue-600 text-white"
              : "rounded-tl-sm bg-white text-gray-800 shadow-sm"
          }`}
        >
          {isUser ? content : <Markdown content={content} />}
        </div>
        {sources && sources.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {sources.map((s) => (
              <button
                key={s.doc_id}
                onClick={() => onDownload?.(s)}
                className="rounded-full border border-gray-200 bg-white px-2.5 py-1 text-xs text-blue-700 hover:bg-blue-50"
                title="下载原文"
              >
                📄 {s.title}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
