"use client";

import { useCallback, useEffect, useState } from "react";
import ConversationSidebar from "@/components/ConversationSidebar";
import Markdown from "@/components/Markdown";
import NavBar from "@/components/NavBar";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type {
  ChatResponse,
  ConversationHistory,
  ConversationSummary,
  SourceRef,
} from "@/lib/types";

interface Turn {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
}

export default function ChatPage() {
  const ready = useAuthGuard();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadConversations = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setConversations(
        await api.get<ConversationSummary[]>(
          `/conversations?workspace_id=${workspaceId}`
        )
      );
    } catch {
      setConversations([]);
    }
  }, [workspaceId]);

  // 切换空间：刷新会话列表，清空当前会话
  useEffect(() => {
    setConversationId(null);
    setTurns([]);
    loadConversations();
  }, [workspaceId, loadConversations]);

  async function selectConversation(id: string) {
    setError(null);
    setConversationId(id);
    try {
      const hist = await api.get<ConversationHistory>(`/conversations/${id}`);
      setTurns(
        hist.messages.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
        }))
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载会话失败");
    }
  }

  function newConversation() {
    // 新会话延迟到首次发消息时由后端创建（conversation_id=null）
    setConversationId(null);
    setTurns([]);
    setError(null);
  }

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
      const isNew = conversationId === null;
      setConversationId(res.conversation_id);
      setTurns((t) => [
        ...t,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
      if (isNew) await loadConversations();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败");
    } finally {
      setBusy(false);
    }
  }

  async function download(source: SourceRef) {
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
    <div className="flex h-screen flex-col">
      <NavBar />
      <div className="flex items-center gap-3 border-b bg-white px-4 py-2">
        <span className="text-sm text-gray-500">空间：</span>
        <WorkspacePicker value={workspaceId} onChange={setWorkspaceId} />
      </div>

      <div className="flex flex-1 overflow-hidden">
        <ConversationSidebar
          conversations={conversations}
          activeId={conversationId}
          onSelect={selectConversation}
          onNew={newConversation}
        />

        <main className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
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
                  className={`inline-block max-w-[85%] rounded-lg px-4 py-2 text-sm ${
                    t.role === "user"
                      ? "whitespace-pre-wrap bg-blue-600 text-white"
                      : "bg-white text-gray-800 shadow-sm"
                  }`}
                >
                  {t.role === "assistant" ? (
                    // 助手回答用 Markdown 渲染（react-markdown 不解析裸 HTML，防 XSS）
                    <Markdown content={t.content} />
                  ) : (
                    t.content
                  )}
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

          {error && <p className="px-4 text-sm text-red-600">{error}</p>}

          <form onSubmit={send} className="flex gap-2 border-t p-4">
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
    </div>
  );
}
