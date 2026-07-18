"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import ConversationSidebar from "@/components/ConversationSidebar";
import Markdown from "@/components/Markdown";
import MessageBubble from "@/components/MessageBubble";
import NavBar from "@/components/NavBar";
import FileAttachPanel from "@/components/chat-plus/FileAttachPanel";
import OutputFileChip from "@/components/chat-plus/OutputFileChip";
import SessionFilesPanel, {
  type SessionFilesHandle,
} from "@/components/chat-plus/SessionFilesPanel";
import SkillPicker from "@/components/chat-plus/SkillPicker";
import WorkspaceDocPicker from "@/components/chat-plus/WorkspaceDocPicker";
import { api, ApiError } from "@/lib/api";
import { isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type { ConversationHistory, ConversationSummary, SourceRef } from "@/lib/types";

interface AttachedFile {
  storage_key: string;
  filename: string;
  size?: number;
}

interface OutputFile {
  filename: string;
  relpath?: string;
  storage_key?: string;
  download_url?: string;
  conversation_id?: string;
}

interface Turn {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  error_key?: string;
  thinking?: string;
  attachments?: AttachedFile[];
  output_files?: OutputFile[];
}

interface DonePayload {
  answer: string;
  sources: SourceRef[];
  conversation_id: string;
  error_key?: string;
}

const SESSION_KEY = "chat_plus_state";

export default function ChatPlusPage() {
  const t = useTranslations("chatPlus");
  const ready = useAuthGuard();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");
  const [error, setError] = useState<string | null>(null);

  // 是否有 skills:write（控制「存为 Skill」显隐；后端仍是唯一防线）
  const [canWriteSkill, setCanWriteSkill] = useState(false);

  // Chat+ extras
  const [activeSkillIds, setActiveSkillIds] = useState<string[]>([]);
  const [docFilterIds, setDocFilterIds] = useState<string[]>([]);
  const [allDocs, setAllDocs] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  // 记录最后一次发送，供出错重试
  const [lastSent, setLastSent] = useState<
    { message: string; attachments: AttachedFile[] } | null
  >(null);
  // pending output files from current stream
  const [pendingOutputFiles, setPendingOutputFiles] = useState<OutputFile[]>([]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const thinkingAccRef = useRef("");
  const sessionFilesRef = useRef<SessionFilesHandle>(null);

  useEffect(() => {
    // 会话不分空间：仅从 sessionStorage 恢复该窗口的当前对话/消息。
    // 工作区是每轮瞬时上下文，不持久化、不影响会话列表。
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        const s = JSON.parse(raw) as {
          conversationId: string | null;
          turns: Turn[];
        };
        setConversationId(s.conversationId);
        setTurns(s.turns);
      }
    } catch {}
  }, []);

  useEffect(() => { return () => { abortRef.current?.abort(); }; }, []);

  // 拉取权限，决定是否显示「存为 Skill」（admin 恒可）
  useEffect(() => {
    if (isAdmin()) {
      setCanWriteSkill(true);
      return;
    }
    api
      .get<Record<string, string>>("/auth/my-permissions")
      .then((perms) => setCanWriteSkill(perms.skills === "write"))
      .catch(() => setCanWriteSkill(false));
  }, []);

  // 会话列表不分空间：列出当前用户全部 chatplus 会话
  const loadConversations = useCallback(async () => {
    try {
      setConversations(
        await api.get<ConversationSummary[]>(`/conversations?source=chatplus`)
      );
    } catch {
      setConversations([]);
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ conversationId, turns }));
    } catch {}
  }, [conversationId, turns]);

  // Skill 是全局的、与空间无关 → 持久化到会话；文档选择随工作区瞬时，不持久化。
  function handleSkillChange(ids: string[]) {
    setActiveSkillIds(ids);
    if (conversationId) {
      api
        .patch(`/conversations/${conversationId}/settings`, { active_skill_ids: ids })
        .catch(() => {});
    }
  }

  function handleDocChange(ids: string[]) {
    setDocFilterIds(ids);
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, busy]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  async function selectConversation(id: string) {
    setError(null);
    setConversationId(id);
    setAttachedFiles([]);
    // 切换会话：工作区/文档是瞬时上下文，一律重置为「不引用」
    setWorkspaceId(null);
    setDocFilterIds([]);
    setAllDocs(false);
    try {
      const hist = await api.get<ConversationHistory>(`/conversations/${id}`);
      setTurns(
        hist.messages.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
          attachments: m.attachments ?? [],
          output_files: m.output_files ?? [],
        }))
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("loadFailed"));
    }
    // 仅恢复该对话保存的 Skill 选择（Skill 全局、与空间无关）
    try {
      const s = await api.get<{ active_skill_ids: string[] }>(
        `/conversations/${id}/settings`
      );
      setActiveSkillIds(s.active_skill_ids ?? []);
    } catch {
      setActiveSkillIds([]);
    }
  }

  function newConversation() {
    setConversationId(null);
    setTurns([]);
    setError(null);
    setAttachedFiles([]);
    // 新建对话：重置 Skill / 工作区 / 文档选择，避免状态污染
    setActiveSkillIds([]);
    setWorkspaceId(null);
    setDocFilterIds([]);
    setAllDocs(false);
    setLastSent(null);
  }

  function stopGeneration() {
    abortRef.current?.abort();
  }

  if (!ready) return null;

  async function sendMessage(message: string, currentAttachments?: AttachedFile[]) {
    if (!message || busy) return;
    setError(null);
    setBusy(true);
    setPendingOutputFiles([]);

    const ac = new AbortController();
    abortRef.current = ac;

    const filesToSend = currentAttachments ?? attachedFiles;
    const isNew = conversationId === null;
    setLastSent({ message, attachments: filesToSend });

    try {
      await api.stream(
        "/chat/plus/stream",
        {
          workspace_id: workspaceId ?? null,
          message,
          conversation_id: conversationId,
          skill_ids: activeSkillIds.length > 0 ? activeSkillIds : null,
          doc_ids: docFilterIds.length > 0 ? docFilterIds : null,
          all_docs: allDocs,
          attachments: filesToSend.length > 0 ? filesToSend : null,
        },
        (event, data) => {
          // 聊天+ 不再展示三步动画，忽略 stage 事件
          if (event === "thinking") {
            thinkingAccRef.current += (data as { text: string }).text;
            setStreamingThinking(thinkingAccRef.current);
          } else if (event === "token") {
            setStreamingText((prev) => prev + (data as { text: string }).text);
          } else if (event === "done") {
            setStreamingText("");
            setStreamingThinking("");
            setLastSent(null);
            const savedThinking = thinkingAccRef.current || undefined;
            thinkingAccRef.current = "";
            const d = data as DonePayload;
            setConversationId(d.conversation_id);
            // 新对话：把本次使用的 Skill 选择保存到该对话（文档随空间瞬时，不持久化）
            if (isNew && activeSkillIds.length > 0) {
              api
                .patch(`/conversations/${d.conversation_id}/settings`, {
                  active_skill_ids: activeSkillIds,
                })
                .catch(() => {});
            }
            setTurns((t) => [
              ...t,
              {
                role: "assistant",
                content: d.answer,
                sources: d.sources,
                error_key: d.error_key,
                thinking: savedThinking,
              },
            ]);
            setBusy(false);
            setConversations((prev) => {
              if (prev.some((c) => c.id === d.conversation_id)) return prev;
              return [
                { id: d.conversation_id, workspace_id: null, title: null, pinned: false, created_at: new Date().toISOString() },
                ...prev,
              ];
            });
          } else if (event === "output_files") {
            const d = data as { files: OutputFile[] };
            setPendingOutputFiles(d.files);
            setTurns((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "assistant") {
                return [
                  ...prev.slice(0, -1),
                  { ...last, output_files: d.files },
                ];
              }
              return prev;
            });
            // 刷新「本会话文件」面板
            sessionFilesRef.current?.refresh();
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
        // user stopped
      } else {
        setError(err instanceof ApiError ? err.message : t("requestFailed"));
      }
    } finally {
      setBusy(false);
      setStreamingText("");
      setStreamingThinking("");
      thinkingAccRef.current = "";
      abortRef.current = null;
      // clear attachments after send
      setAttachedFiles([]);
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message) return;
    setInput("");
    const sentAttachments = [...attachedFiles];
    setTurns((t) => [...t, { role: "user", content: message, attachments: sentAttachments }]);
    await sendMessage(message, sentAttachments);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(e as unknown as React.FormEvent);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      <NavBar />

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
          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
            {turns.length === 0 && !busy && (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-purple-100 text-purple-600">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-600">{t("emptyTitle")}</p>
                <p className="mt-1 text-xs text-gray-400">{t("emptyHint")}</p>
              </div>
            )}

            {turns.map((turn, i) => (
              <div key={i}>
                {turn.role === "assistant" && turn.thinking && (
                  <details className="mb-1 ml-11">
                    <summary className="cursor-pointer select-none text-xs text-gray-400 hover:text-gray-600">
                      思考过程
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
                  onDownload={async () => {}}
                />
                {turn.role === "user" && turn.attachments && turn.attachments.length > 0 && (
                  <div className="ml-11 mt-1 flex flex-wrap gap-1">
                    {turn.attachments.map((f) => (
                      <span
                        key={f.storage_key}
                        className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500"
                      >
                        {f.filename}
                      </span>
                    ))}
                  </div>
                )}
                {turn.role === "assistant" && turn.output_files && turn.output_files.length > 0 && (
                  <div className="ml-11 mt-1">
                    <OutputFileChip files={turn.output_files} conversationId={conversationId} canWriteSkill={canWriteSkill} />
                  </div>
                )}
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
                      <p className="mb-1 text-xs font-medium text-gray-400">{t("thinking")}</p>
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
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white text-xs font-semibold text-gray-700 shadow-sm">
                  AI
                </div>
                <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 shadow-sm">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-purple-400" />
                  <span className="text-sm text-gray-400">{t("thinkingDots")}</span>
                </div>
              </div>
            ) : null}
          </div>

          {error && (
            <div className="mx-4 mb-2 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <span>{error}</span>
              {lastSent && !busy && (
                <button
                  type="button"
                  onClick={() => sendMessage(lastSent.message, lastSent.attachments)}
                  className="shrink-0 rounded-md border border-red-300 bg-white px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-100"
                >
                  {t("retry")}
                </button>
              )}
            </div>
          )}

          {/* Input area */}
          <div className="border-t border-gray-200 bg-white px-4 py-3">
            {/* Chat+ toolbar：Skill / 工作区(可选，引用文档) / 附件 */}
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <SkillPicker selectedIds={activeSkillIds} onChange={handleSkillChange} />
              <WorkspaceDocPicker
                workspaceId={workspaceId}
                onWorkspaceChange={setWorkspaceId}
                docIds={docFilterIds}
                onDocsChange={handleDocChange}
                allDocs={allDocs}
                onAllDocsChange={setAllDocs}
              />
              <FileAttachPanel files={attachedFiles} onChange={setAttachedFiles} />
              <SessionFilesPanel ref={sessionFilesRef} conversationId={conversationId} canWriteSkill={canWriteSkill} />
            </div>

            <form onSubmit={send}>
              <div className="flex items-end gap-3 rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 focus-within:border-purple-500 focus-within:ring-1 focus-within:ring-purple-500 transition-all">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={t("inputPlaceholder")}
                  disabled={busy}
                  rows={1}
                  className="flex-1 resize-none bg-transparent text-sm text-gray-900 placeholder-gray-400 outline-none disabled:opacity-60"
                  style={{ minHeight: "1.5rem", maxHeight: "10rem" }}
                />
                {busy ? (
                  <button
                    type="button"
                    onClick={stopGeneration}
                    className="shrink-0 rounded-lg border border-gray-300 bg-white p-2 text-gray-600 hover:bg-gray-100 transition-colors"
                    title={t("stopGenerating")}
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    </svg>
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim()}
                    className="shrink-0 rounded-lg bg-purple-600 p-2 text-white hover:bg-purple-700 disabled:bg-gray-300 disabled:text-gray-500 transition-colors"
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
