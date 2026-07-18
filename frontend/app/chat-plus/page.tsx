"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import ConversationSidebar from "@/components/ConversationSidebar";
import Markdown from "@/components/Markdown";
import MessageBubble from "@/components/MessageBubble";
import NavBar from "@/components/NavBar";
import AskUserOptions from "@/components/chat-plus/AskUserOptions";
import FileAttachPanel from "@/components/chat-plus/FileAttachPanel";
import OutputFileChip from "@/components/chat-plus/OutputFileChip";
import SessionFilesPanel, {
  type SessionFilesHandle,
} from "@/components/chat-plus/SessionFilesPanel";
import SkillPicker from "@/components/chat-plus/SkillPicker";
import WorkspaceDocPicker from "@/components/chat-plus/WorkspaceDocPicker";
import { api, ApiError } from "@/lib/api";
import { parseAskUser } from "@/lib/askUser";
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

type StreamBlock =
  | { type: "thinking"; text: string }
  | { type: "text"; text: string };

const SESSION_KEY = "chat_plus_state";

export default function ChatPlusPage() {
  const t = useTranslations("chatPlus");
  const ready = useAuthGuard("chatplus");
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [streamingBlocks, setStreamingBlocks] = useState<StreamBlock[]>([]);
  const [error, setError] = useState<string | null>(null);
  // 正在后台生成的会话 id 集合（侧边栏指示器；后端 /chat/plus/active 轮询）
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());

  // 是否有 skills:write（控制「存为 Skill」显隐；后端仍是唯一防线）
  const [canWriteSkill, setCanWriteSkill] = useState(false);

  // Chat+ extras
  const [activeSkillIds, setActiveSkillIds] = useState<string[]>([]);
  const [docFilterIds, setDocFilterIds] = useState<string[]>([]);
  const [allDocs, setAllDocs] = useState(false);
  // 交互模式：开时后端注入 ask-user 协议，模型可弹选项让用户澄清（瞬时，不持久化）
  const [interactive, setInteractive] = useState(false);
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
  const streamingBlocksRef = useRef<StreamBlock[]>([]);
  const sessionFilesRef = useRef<SessionFilesHandle>(null);
  // 保证「挂载后自动重连」只触发一次（同标签页返回场景）
  const mountReconnectDoneRef = useRef(false);

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

  // unmount：仅断开本地 SSE 订阅（后端生成继续跑）。取消生成只走「停止」按钮。
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

  // 轮询「正在生成中的会话」，驱动侧边栏指示器（~5s）
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const r = await api.get<{ conversation_ids: string[] }>("/chat/plus/active");
        if (!cancelled) setActiveIds(new Set(r.conversation_ids));
      } catch {
        /* 忽略瞬时失败 */
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ conversationId, turns }));
    } catch {}
  }, [conversationId, turns]);

  // 同标签页返回：从 sessionStorage 恢复的会话若仍在后台生成，自动重连一次
  useEffect(() => {
    if (mountReconnectDoneRef.current) return;
    if (activeIds.size === 0) return;
    mountReconnectDoneRef.current = true;
    if (conversationId && activeIds.has(conversationId) && !busy) {
      reconnectStream(conversationId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIds]);

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
    if (!busy) { setElapsed(0); return; }
    setElapsed(0);
    const start = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(id);
  }, [busy]);

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
    // 若该会话仍在后台生成，重连实时流续看答案
    if (activeIds.has(id)) {
      reconnectStream(id);
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
    setInteractive(false);
    setLastSent(null);
  }

  function stopGeneration() {
    // 只有显式停止才取消后端生成；断连（切页面）不取消（见 unmount 注释）
    if (conversationId) {
      api.post(`/chat/plus/stop/${conversationId}`).catch(() => {});
    }
    abortRef.current?.abort();
  }

  async function handleEdit(turnIndex: number, newContent: string) {
    const newTurns = turns.slice(0, turnIndex);
    const originalAttachments = turns[turnIndex]?.attachments ?? [];
    newTurns.push({ role: "user", content: newContent, attachments: originalAttachments });
    setTurns(newTurns);
    await sendMessage(newContent, originalAttachments);
  }

  if (!ready) return null;

  // 共享的 SSE 事件处理器：POST 首发与 GET 重连走同一套逻辑。
  // isNew 仅在首发新会话时用于保存 Skill 选择。
  function makeStreamHandler(isNew: boolean) {
    return (event: string, data: unknown) => {
      // 聊天+ 不再展示三步动画，忽略 stage 事件
      if (event === "thinking") {
        const text = (data as { text: string }).text;
        setStreamingBlocks((prev) => {
          const last = prev[prev.length - 1];
          const next = last?.type === "thinking"
            ? [...prev.slice(0, -1), { type: "thinking" as const, text: last.text + text }]
            : [...prev, { type: "thinking" as const, text }];
          streamingBlocksRef.current = next;
          return next;
        });
      } else if (event === "token") {
        const text = (data as { text: string }).text;
        setStreamingBlocks((prev) => {
          const last = prev[prev.length - 1];
          const next = last?.type === "text"
            ? [...prev.slice(0, -1), { type: "text" as const, text: last.text + text }]
            : [...prev, { type: "text" as const, text }];
          streamingBlocksRef.current = next;
          return next;
        });
      } else if (event === "done") {
        const thinkingText = streamingBlocksRef.current
          .filter((b) => b.type === "thinking")
          .map((b) => b.text)
          .join("") || undefined;
        streamingBlocksRef.current = [];
        setStreamingBlocks([]);
        const d = data as DonePayload;
        setTurns((t) => [
          ...t,
          {
            role: "assistant",
            content: d.answer,
            sources: d.sources,
            error_key: d.error_key,
            thinking: thinkingText,
          },
        ]);
        setLastSent(null);
        setConversationId(d.conversation_id);
        // 新对话：把本次使用的 Skill 选择保存到该对话（文档随空间瞬时，不持久化）
        if (isNew && activeSkillIds.length > 0) {
          api
            .patch(`/conversations/${d.conversation_id}/settings`, {
              active_skill_ids: activeSkillIds,
            })
            .catch(() => {});
        }
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
    };
  }

  // 重连正在后台运行的生成流（切回会话 / 首发 409 时）。
  async function reconnectStream(convId: string) {
    setError(null);
    setBusy(true);
    setPendingOutputFiles([]);
    streamingBlocksRef.current = [];
    setStreamingBlocks([]);
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await api.streamGet(
        `/chat/plus/stream/${convId}`,
        makeStreamHandler(false),
        ac.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // 切走/停止：不报错
      } else if (err instanceof ApiError && err.status === 404) {
        // 生成已结束且过了保留窗口——历史里已有结果，静默
      } else {
        setError(err instanceof ApiError ? err.message : t("requestFailed"));
      }
    } finally {
      setBusy(false);
      setStreamingBlocks([]);
      streamingBlocksRef.current = [];
      abortRef.current = null;
    }
  }

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
          interactive,
          attachments: filesToSend.length > 0 ? filesToSend : null,
        },
        makeStreamHandler(isNew),
        ac.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // user stopped
      } else if (err instanceof ApiError && err.status === 409 && conversationId) {
        // 该会话已有生成在跑（重复发送）：透明切换为订阅同一路流
        setAttachedFiles([]);
        abortRef.current = null;
        await reconnectStream(conversationId);
        return;
      } else {
        setError(err instanceof ApiError ? err.message : t("requestFailed"));
      }
    } finally {
      setBusy(false);
      setStreamingBlocks([]);
      streamingBlocksRef.current = [];
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
          generatingIds={activeIds}
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

            {turns.map((turn, i) => {
              // assistant 消息：解析 ask-user 块，正文剥离后渲染，选项单独渲染成按钮
              const parsed =
                turn.role === "assistant" ? parseAskUser(turn.content) : null;
              const displayContent = parsed ? parsed.clean : turn.content;
              const askDisabled = busy || i !== turns.length - 1;
              return (
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
                {(displayContent || turn.role === "user") && (
                  <MessageBubble
                    role={turn.role}
                    content={displayContent}
                    sources={turn.sources}
                    errorKey={turn.error_key}
                    onDownload={async () => {}}
                    onEdit={turn.role === "user" && !busy ? (newContent) => handleEdit(i, newContent) : undefined}
                  />
                )}
                {parsed?.ask && (
                  <AskUserOptions
                    payload={parsed.ask}
                    onPick={(text) => {
                      setTurns((t) => [...t, { role: "user", content: text }]);
                      sendMessage(text);
                    }}
                    disabled={askDisabled}
                  />
                )}
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
              );
            })}

            {busy && streamingBlocks.length > 0 ? (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white text-xs font-semibold text-gray-700 shadow-sm">
                  AI
                </div>
                <div className="max-w-[75%] space-y-2">
                  {streamingBlocks.map((block, idx) =>
                    block.type === "thinking" ? (
                      <div key={idx} className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2">
                        <p className="mb-1 flex items-center gap-2 text-xs font-medium text-gray-400">
                          {t("thinking")}
                          <span className="font-mono tabular-nums">{elapsed}s</span>
                        </p>
                        <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-500">{block.text}</p>
                      </div>
                    ) : (
                      <div key={idx} className="rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 text-sm leading-relaxed text-gray-900 shadow-sm">
                        <Markdown content={block.text} />
                      </div>
                    )
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
                  <span className="font-mono tabular-nums text-xs text-gray-400">{elapsed}s</span>
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
              <button
                type="button"
                onClick={() => setInteractive((v) => !v)}
                title="交互模式：需要澄清时弹出选项让你选择"
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm transition-colors ${
                  interactive
                    ? "border-purple-400 bg-purple-50 text-purple-700"
                    : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${interactive ? "bg-purple-500" : "bg-gray-300"}`}
                />
                交互模式
              </button>
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
