"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import ConversationSidebar from "@/components/ConversationSidebar";
import Markdown from "@/components/Markdown";
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
  error_key?: string;
  thinking?: string;
}

interface DonePayload {
  answer: string;
  sources: SourceRef[];
  conversation_id: string;
  error_key?: string;
}

const SESSION_KEY = "chat_state";

export default function ChatPage() {
  const t = useTranslations("chat");
  const ready = useAuthGuard("chat");
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [stageKey, setStageKey] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [interrupted, setInterrupted] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // 用 ref 累积 thinking，绕过闭包捕获旧 state 的问题
  const thinkingAccRef = useRef("");
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
          `/conversations?workspace_id=${workspaceId}&source=chat`
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

  // 随空间切换拉取该空间引导问题（未配置时后端回退全局默认）
  useEffect(() => {
    if (!workspaceId) { setSuggestedQuestions([]); return; }
    api.get<{ questions: string[] }>(`/settings/workspaces/${workspaceId}/suggested-questions`)
      .then((r) => setSuggestedQuestions(r.questions))
      .catch(() => setSuggestedQuestions([]));
  }, [workspaceId]);

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
      setError(err instanceof ApiError ? err.message : t("load_failed"));
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
    setStage(t("preparing"));

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
            const { stage: sk, message_key, message_params } = data as {
              stage: string;
              message_key: string;
              message_params: Record<string, unknown>;
            };
            setStageKey(sk);
            setStage(t(message_key, message_params as Record<string, string>));
          } else if (event === "thinking") {
            thinkingAccRef.current += (data as { text: string }).text;
            setStreamingThinking(thinkingAccRef.current);
          } else if (event === "token") {
            setStreamingText((prev) => prev + (data as { text: string }).text);
          } else if (event === "done") {
            setStreamingText("");
            setStreamingThinking("");
            const savedThinking = thinkingAccRef.current || undefined;
            thinkingAccRef.current = "";
            const d = data as DonePayload;
            setConversationId(d.conversation_id);
            setTurns((t) => [
              ...t,
              { role: "assistant", content: d.answer, sources: d.sources, error_key: d.error_key, thinking: savedThinking },
            ]);
            // 立即结束 busy 状态，不等侧边栏刷新
            setBusy(false);
            setStage(null);
            setStageKey(null);
            // 新会话先加一条占位记录，等 title 事件到来再更新
            setConversations((prev) => {
              if (prev.some((c) => c.id === d.conversation_id)) return prev;
              return [
                { id: d.conversation_id, workspace_id: workspaceId ?? "", title: null, pinned: false, created_at: new Date().toISOString() },
                ...prev,
              ];
            });
          } else if (event === "title") {
            const d = data as { conversation_id: string; title: string };
            setConversations((prev) =>
              prev.map((c) => (c.id === d.conversation_id ? { ...c, title: d.title } : c))
            );
          }
        },
        ac.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // user stopped — keep turns as-is
      } else {
        setError(err instanceof ApiError ? err.message : t("request_failed"));
      }
    } finally {
      setBusy(false);
      setStage(null);
      setStageKey(null);
      setStreamingText("");
      setStreamingThinking("");
      thinkingAccRef.current = "";
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
      setError(t("download_failed"));
    }
  }

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <NavBar />

      {/* Workspace toolbar */}
      <div className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-2 shadow-sm">
        <span className="text-sm text-gray-500">{t("workspace_label")}</span>
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
                <p className="text-sm font-medium text-gray-600">{t("ask_title")}</p>
                <p className="mt-1 text-xs text-gray-400">{t("ask_subtitle")}</p>
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
            {turns.map((turn, i) => (
              <div key={i}>
                {turn.role === "assistant" && turn.thinking && (
                  <details className="mb-1 ml-11">
                    <summary className="cursor-pointer select-none text-xs text-gray-400 hover:text-gray-600">
                      {t("thinking_label")}
                    </summary>
                    <div className="mt-1 rounded-xl border border-gray-100 bg-gray-50 px-3 py-2">
                      <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-500">{turn.thinking}</p>
                    </div>
                  </details>
                )}
                <MessageBubble
                  role={turn.role}
                  content={turn.content}
                  sources={turn.sources}
                  errorKey={turn.error_key}
                  onDownload={download}
                  onEdit={turn.role === "user" && !busy ? (newContent) => handleEdit(i, newContent) : undefined}
                  onResend={interrupted && !busy && turn.role === "user" && i === turns.length - 1 ? () => sendMessage(turn.content) : undefined}
                />
              </div>
            ))}
{busy && (streamingThinking || streamingText) ? (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white text-xs font-semibold text-gray-700 shadow-sm">
                  AI
                </div>
                <div className="max-w-[75%] space-y-2">
                  {streamingThinking && (
                    <div className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2">
                      <p className="mb-1 text-xs font-medium text-gray-400">{t("thinking_label")}</p>
                      <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-500">{streamingThinking}</p>
                    </div>
                  )}
                  {streamingText && (
                    <div className="rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 text-sm leading-relaxed text-gray-900 shadow-sm">
                      <Markdown content={streamingText} />
                    </div>
                  )}
                </div>
              </div>
            ) : busy ? (
              <ThinkingBubble stage={stage} stageKey={stageKey} />
            ) : null}
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
                  placeholder={workspaceId ? t("ask_placeholder") : t("select_workspace_placeholder")}
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
                    title={t("stop_generating")}
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
