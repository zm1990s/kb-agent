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

const SESSION_KEY = "chat_state";

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
  const [interrupted, setInterrupted] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // 标记正在从 sessionStorage 恢复，避免 workspace 变更 effect 重置 turns
  const restoringRef = useRef(false);

  // 从 sessionStorage 恢复（仅挂载时）
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) return;
      const s = JSON.parse(raw) as {
        workspaceId: string;
        conversationId: string | null;
        turns: Turn[];
      };
      restoringRef.current = true;
      setWorkspaceId(s.workspaceId);
      setConversationId(s.conversationId);
      setTurns(s.turns);
      // 最后一条是 user 说明 assistant 回复未收到
      if (s.turns.length > 0 && s.turns[s.turns.length - 1].role === "user") {
        setInterrupted(true);
      }
    } catch {}
  }, []);

  // unmount 时 abort 正在进行的流
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

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
    // 恢复时只加载会话列表，不重置当前对话状态
    if (restoringRef.current) {
      restoringRef.current = false;
      loadConversations();
      return;
    }
    setConversationId(null);
    setTurns([]);
    loadConversations();
  }, [workspaceId, loadConversations]);

  // 持久化到 sessionStorage
  useEffect(() => {
    if (!workspaceId) return;
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ workspaceId, conversationId, turns }));
    } catch {}
  }, [workspaceId, conversationId, turns]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, stage, busy]);

  // 拉取引导问题（仅挂载时一次）
  useEffect(() => {
    api.get<{ questions: string[] }>("/settings/suggested-questions")
      .then((r) => setSuggestedQuestions(r.questions))
      .catch(() => {});
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

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

  function stopGeneration() {
    abortRef.current?.abort();
  }

  if (!ready) return null;

  async function sendMessage(message: string, historyOverride?: Turn[]) {
    if (!message || !workspaceId || busy) return;
    setError(null);
    setInterrupted(false);
    setBusy(true);
    setStage("正在准备…");

    const ac = new AbortController();
    abortRef.current = ac;

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
        },
        ac.signal,
      );
      await loadConversations();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // user stopped — keep turns as-is
      } else {
        setError(err instanceof ApiError ? err.message : "请求失败");
      }
    } finally {
      setBusy(false);
      setStage(null);
      abortRef.current = null;
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", content: message }]);
    await sendMessage(message);
  }

  async function handleEdit(turnIndex: number, newContent: string) {
    // Truncate turns up to and including the edited user message, then re-send
    const newTurns = turns.slice(0, turnIndex);
    newTurns.push({ role: "user", content: newContent });
    setTurns(newTurns);
    await sendMessage(newContent);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(e as unknown as React.FormEvent);
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
    <div className="flex h-screen flex-col bg-gray-50">
      <NavBar />

      {/* Workspace toolbar */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-2 shadow-sm">
        <span className="text-sm text-gray-500">空间：</span>
        <WorkspacePicker value={workspaceId} onChange={setWorkspaceId} />
      </div>

      <div className="flex flex-1 overflow-hidden">
        <ConversationSidebar
          conversations={conversations}
          activeId={conversationId}
          onSelect={selectConversation}
          onNew={newConversation}
          onUpdated={(updated) =>
            setConversations((prev) =>
              prev
                .map((c) => (c.id === updated.id ? updated : c))
                .sort((a, b) => {
                  if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
                  return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
                })
            )
          }
          onDeleted={(id) => {
            setConversations((prev) => prev.filter((c) => c.id !== id));
            if (conversationId === id) newConversation();
          }}
        />

        <main className="flex flex-1 flex-col overflow-hidden">
          {/* Messages area */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
            {turns.length === 0 && !busy && (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-100 text-blue-600">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-600">向知识库提问</p>
                <p className="mt-1 text-xs text-gray-400">AI 会基于文档智能作答并附上原文来源</p>
                {suggestedQuestions.length > 0 && (
                  <div className="mt-6 flex flex-col gap-2 w-full max-w-md px-4">
                    {suggestedQuestions.map((q) => (
                      <button
                        key={q}
                        onClick={() => sendMessage(q)}
                        className="rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-left text-sm text-gray-700 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 transition-colors shadow-sm"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {turns.map((t, i) => (
              <MessageBubble
                key={i}
                role={t.role}
                content={t.content}
                sources={t.sources}
                onDownload={download}
                onEdit={t.role === "user" && !busy ? (newContent) => handleEdit(i, newContent) : undefined}
                onResend={interrupted && !busy && t.role === "user" && i === turns.length - 1 ? () => sendMessage(t.content) : undefined}
              />
            ))}
{busy && <ThinkingBubble stage={stage} />}
          </div>

          {error && (
            <div className="mx-4 mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* Input area */}
          <div className="border-t border-gray-200 bg-white px-4 py-3">
            <form onSubmit={send}>
              <div className="flex items-end gap-3 rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 transition-all">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={workspaceId ? "输入问题… (Enter 发送，Shift+Enter 换行)" : "请先选择空间"}
                  disabled={!workspaceId || busy}
                  rows={1}
                  className="flex-1 resize-none bg-transparent text-sm text-gray-900 placeholder-gray-400 outline-none disabled:opacity-60"
                  style={{ minHeight: "1.5rem", maxHeight: "10rem" }}
                />
                {busy ? (
                  <button
                    type="button"
                    onClick={stopGeneration}
                    className="shrink-0 rounded-lg border border-gray-300 bg-white p-2 text-gray-600 hover:bg-gray-100 transition-colors"
                    title="停止生成"
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    </svg>
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!workspaceId || !input.trim()}
                    className="shrink-0 rounded-lg bg-blue-600 p-2 text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-500 transition-colors"
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
                    </svg>
                  </button>
                )}
              </div>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}
