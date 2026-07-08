"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ConversationSidebar from "@/components/ConversationSidebar";
import MessageBubble from "@/components/MessageBubble";
import NavBar from "@/components/NavBar";
import ThinkingBubble from "@/components/ThinkingBubble";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type {
  ConversationHistory,
  ConversationSummary,
  SourceRef,
} from "@/lib/types";

interface Turn {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
}

interface DonePayload {
  answer: string;
  sources: SourceRef[];
  conversation_id: string;
}

export default function ChatPage() {
  const ready = useAuthGuard();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    setConversationId(null);
    setTurns([]);
    loadConversations();
  }, [workspaceId, loadConversations]);

  // 新消息或阶段变化时滚到底部
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, stage, busy]);

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
    setConversationId(null);
    setTurns([]);
    setError(null);
  }

  if (!ready) return null;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || !workspaceId || busy) return;
    setError(null);
    setInput("");
    setTurns((t) => [...t, { role: "user", content: message }]);
    setBusy(true);
    setStage("正在准备…");

    const isNew = conversationId === null;
    try {
      await api.stream(
        "/chat/stream",
        {
          workspace_id: workspaceId,
          message,
          conversation_id: conversationId,
        },
        (event, data) => {
          if (event === "stage") {
            setStage((data as { message: string }).message);
          } else if (event === "done") {
            const d = data as DonePayload;
            setConversationId(d.conversation_id);
            setTurns((t) => [
              ...t,
              { role: "assistant", content: d.answer, sources: d.sources },
            ]);
          }
        }
      );
      if (isNew) await loadConversations();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "请求失败");
    } finally {
      setBusy(false);
      setStage(null);
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

        <main className="flex flex-1 flex-col overflow-hidden bg-gray-50">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-6">
            {turns.length === 0 && !busy && (
              <p className="mt-8 text-center text-sm text-gray-400">
                向知识库提问，AI 会基于文档智能作答并附上原文来源。
              </p>
            )}
            {turns.map((t, i) => (
              <MessageBubble
                key={i}
                role={t.role}
                content={t.content}
                sources={t.sources}
                onDownload={download}
              />
            ))}
            {busy && <ThinkingBubble stage={stage} />}
          </div>

          {error && <p className="px-6 text-sm text-red-600">{error}</p>}

          <form onSubmit={send} className="flex gap-2 border-t bg-white p-4">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={workspaceId ? "输入问题…" : "请先选择空间"}
              disabled={!workspaceId || busy}
              className="flex-1 rounded-full border px-4 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!workspaceId || busy || !input.trim()}
              className="rounded-full bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {busy ? "…" : "发送"}
            </button>
          </form>
        </main>
      </div>
    </div>
  );
}
