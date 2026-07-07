"use client";

import { useState } from "react";
import NavBar from "@/components/NavBar";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type { ChatResponse, SourceRef } from "@/lib/types";

interface Turn {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
}

export default function ChatPage() {
  const ready = useAuthGuard();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!ready) return null;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || !workspaceId) return;
    setError(null);
    setInput("");
    setTurns((t) => [...t, { role: "user", content: message }]);
    setBusy(true);
    try {
      const res = await api.post<ChatResponse>("/chat", {
        workspace_id: workspaceId,
        message,
        conversation_id: conversationId,
      });
      setConversationId(res.conversation_id);
      setTurns((t) => [
        ...t,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败");
    } finally {
      setBusy(false);
    }
  }

  async function download(source: SourceRef) {
    // 下载走鉴权端点（download_url 形如 /documents/download?...，此处用文档下载端点）
    try {
      const token = getToken();
      const res = await fetch(`/api/documents/${source.doc_id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = source.title;
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

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col p-4">
        <div className="flex-1 space-y-4">
          {turns.length === 0 && (
            <p className="mt-8 text-center text-sm text-gray-400">
              向知识库提问，回答将附带原文来源。
            </p>
          )}
          {turns.map((t, i) => (
            <div
              key={i}
              className={t.role === "user" ? "text-right" : "text-left"}
            >
              <div
                className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm ${
                  t.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-800 shadow-sm"
                }`}
              >
                {/* 纯文本渲染，不解析 HTML/Markdown —— 杜绝存储型 XSS (SECURITY #6) */}
                {t.content}
              </div>
              {t.sources && t.sources.length > 0 && (
                <div className="mt-1 space-y-1 text-left">
                  <p className="text-xs text-gray-400">来源：</p>
                  {t.sources.map((s) => (
                    <button
                      key={s.doc_id}
                      onClick={() => download(s)}
                      className="mr-2 rounded bg-gray-100 px-2 py-1 text-xs text-blue-700 hover:bg-gray-200"
                    >
                      ↓ {s.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        <form onSubmit={send} className="mt-4 flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={workspaceId ? "输入问题…" : "请先选择空间"}
            disabled={!workspaceId || busy}
            className="flex-1 rounded border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!workspaceId || busy || !input.trim()}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? "…" : "发送"}
          </button>
        </form>
      </main>
    </div>
  );
}
