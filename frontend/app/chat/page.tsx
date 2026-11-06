"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import ConversationSidebar from "@/components/ConversationSidebar";
import ExportConversationModal from "@/components/ExportConversationModal";
import Markdown from "@/components/Markdown";
import MessageBubble from "@/components/MessageBubble";
import NavBar from "@/components/NavBar";
import ThinkingBubble from "@/components/ThinkingBubble";
import AgentProgress from "@/components/AgentProgress";
import WorkspacePicker from "@/components/WorkspacePicker";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type {
  ConversationHistory,
  ConversationSummary,
  SourceRef,
  AgentRun,
  RetrievalAgent,
  RetrievalSource,
} from "@/lib/types";

interface Turn {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  error_key?: string;
  warning?: string;
  thinking?: string;
  agent_runs?: AgentRun[];
}

interface DonePayload {
  answer: string;
  sources: SourceRef[];
  conversation_id: string;
  error_key?: string;
  warning?: string;
  agent_runs?: AgentRun[];
}

function historyTurns(history: ConversationHistory): Turn[] {
  return history.messages.map((m) => ({
    role: m.role,
    content: m.content,
    sources: m.sources,
    error_key: m.retrieval?.error_key ?? undefined,
    agent_runs: m.retrieval?.agent_runs,
    warning: m.retrieval?.warning,
  }));
}

interface StreamMetaPayload {
  conversation_id: string;
  started_at?: number;
  elapsed_seconds?: number;
}

interface ActiveGeneration {
  conversation_id: string;
  started_at: number;
  elapsed_seconds?: number;
}

interface ActiveGenerationsResponse {
  conversation_ids: string[];
  generations?: ActiveGeneration[];
}

const SESSION_KEY = "chat_state";

// SSE 中断后自动重连：最多 3 次，退避 1s / 2s / 4s
const RECONNECT_BACKOFF_MS = [1000, 2000, 4000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const epochSecondsToMs = (seconds: number) => Math.max(0, seconds * 1000);
// 由服务器「已运行秒数」反推本机时钟锚点，之后计时全程用 Date.now() - anchor，免疫时钟偏移
const startAnchorMs = (g: { started_at?: number; elapsed_seconds?: number }): number | null => {
  if (typeof g.elapsed_seconds === "number") {
    return Date.now() - Math.max(0, g.elapsed_seconds) * 1000;
  }
  if (typeof g.started_at === "number") return epochSecondsToMs(g.started_at);
  return null;
};
const activeResponseIds = (r: ActiveGenerationsResponse) =>
  r.generations && r.generations.length > 0
    ? r.generations.map((g) => g.conversation_id)
    : r.conversation_ids;

export default function ChatPage() {
  const t = useTranslations("chat");
  const ready = useAuthGuard("chat");
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [retrievalSources, setRetrievalSources] = useState<RetrievalSource[]>(["workspace"]);
  const [availableAgents, setAvailableAgents] = useState<RetrievalAgent[]>([]);
  const [agentsError, setAgentsError] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [stageKey, setStageKey] = useState<string | null>(null);
  const [agentProgress, setAgentProgress] = useState<AgentRun[] | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [interrupted, setInterrupted] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [exportOpen, setExportOpen] = useState(false);
  // 正在后台生成的会话（侧边栏跳动圆点 + 重连恢复计时；轮询 /chat/active）
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());
  const [activeStartedAtById, setActiveStartedAtById] = useState<Record<string, number>>({});
  const [generationStartedAtMs, setGenerationStartedAtMs] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // 用 ref 累积 thinking，绕过闭包捕获旧 state 的问题
  const thinkingAccRef = useRef("");
  // 标记正在从 sessionStorage 恢复，避免 workspace 变更 effect 重置 turns
  const restoredOnceRef = useRef(false);
  const previousWorkspaceRef = useRef<string | null>(null);
  const [storageRestored, setStorageRestored] = useState(false);
  // 保证「挂载后自动重连」只触发一次（同标签页返回场景）
  const mountReconnectDoneRef = useRef(false);
  // 重连模式：收到重连流首个 thinking/token 时先清空一次再累积（幂等重建）
  const reconnectFreshRef = useRef(false);
  // 追踪最新 conversation_id，供异步 catch 读取（新会话经 meta 事件中途才知晓）
  const conversationIdRef = useRef<string | null>(null);
  // 首次 /chat/active 轮询是否已返回——interrupted 兜底须等它，避免误判
  const firstPollDoneRef = useRef(false);

  // Restore once before writing: React Strict Mode replays mount effects.
  useEffect(() => {
    if (restoredOnceRef.current) return;
    restoredOnceRef.current = true;
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (!raw) return;
      const s = JSON.parse(raw) as {
        workspaceId: string | null;
        conversationId: string | null;
        turns: Turn[];
        retrievalSources?: RetrievalSource[];
      };
      previousWorkspaceRef.current = s.workspaceId;
      setWorkspaceId(s.workspaceId);
      if (Array.isArray(s.retrievalSources)) {
        setRetrievalSources(s.retrievalSources.filter((id) =>
          ["workspace", "paloalto_kb", "paloalto_live", "paloalto_docs"].includes(id)));
      }
      setConversationId(s.conversationId);
      setTurns(s.turns);
      // Earlier shortcut sends cached only the answer. Recover the saved user
      // question without overwriting any navigation or messages added meanwhile.
      if (s.conversationId && s.turns[0]?.role === "assistant") {
        api.get<ConversationHistory>(`/conversations/${s.conversationId}`)
          .then((history) => {
            if (history.messages[0]?.role !== "user") return;
            setTurns((current) => current === s.turns ? historyTurns(history) : current);
          })
          .catch(() => { /* Keep cached answers if history is temporarily unavailable. */ });
      }
      // 注：不在此立即设 interrupted——先等 /chat/active 轮询确认该会话是否仍在后台生成，
      // 若在生成则自动重连续看；仅当确认无任务且最后一条是 user 时才提示重发。
    } catch {} finally {
      setStorageRestored(true);
    }
  }, []);

  useEffect(() => {
    api.get<RetrievalAgent[]>("/chat/agents")
      .then(setAvailableAgents)
      .catch(() => setAgentsError(true));
  }, []);

  // unmount 时 abort（现在语义是"退订"，后台生成任务继续跑）
  useEffect(() => {
    return () => { abortRef.current?.abort(); };
  }, []);

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  // 轮询「正在生成中的会话」，驱动侧边栏指示器 + 重连恢复计时（~5s）
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const r = await api.get<ActiveGenerationsResponse>("/chat/active");
        if (cancelled) return;
        const generations = r.generations ?? [];
        setActiveIds(new Set(activeResponseIds(r)));
        setActiveStartedAtById(
          Object.fromEntries(
            generations
              .map((g) => [g.conversation_id, startAnchorMs(g)] as const)
              .filter((e): e is readonly [string, number] => e[1] !== null)
          )
        );
      } catch {
        /* 忽略瞬时失败 */
      } finally {
        firstPollDoneRef.current = true;
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // 计时器：基于本机时钟锚点（generationStartedAtMs），切走再切回不归零
  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      setGenerationStartedAtMs(null);
      return;
    }
    const start = generationStartedAtMs ?? Date.now();
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [busy, generationStartedAtMs]);

  // 同标签页返回：从 sessionStorage 恢复的会话若仍在后台生成，自动重连一次
  useEffect(() => {
    if (mountReconnectDoneRef.current) return;
    if (activeIds.size === 0) return;
    mountReconnectDoneRef.current = true;
    if (conversationId && activeIds.has(conversationId) && !busy) {
      setGenerationStartedAtMs(activeStartedAtById[conversationId] ?? null);
      reconnectStream(conversationId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIds]);

  // interrupted 兜底：仅当首次轮询已返回、该会话确认不在后台生成、且最后一条是 user 时提示重发
  useEffect(() => {
    if (busy || interrupted) return;
    if (!firstPollDoneRef.current) return;
    if (conversationId && activeIds.has(conversationId)) return;
    if (turns.length > 0 && turns[turns.length - 1].role === "user") {
      setInterrupted(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIds, turns, busy]);

  const loadConversations = useCallback(async () => {
    try {
      const qs = workspaceId
        ? `workspace_id=${workspaceId}&source=chat`
        : `source=chat`;
      setConversations(
        await api.get<ConversationSummary[]>(`/conversations?${qs}`)
      );
    } catch {
      setConversations([]);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (!storageRestored) return;
    if (previousWorkspaceRef.current !== workspaceId) {
      setConversationId(null);
      setTurns([]);
      previousWorkspaceRef.current = workspaceId;
    }
    loadConversations();
  }, [workspaceId, loadConversations, storageRestored]);

  // 持久化到 sessionStorage（workspaceId=null 表示"自动"，也需持久化）
  useEffect(() => {
    if (!storageRestored) return;
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ workspaceId, conversationId, turns, retrievalSources }));
    } catch {}
  }, [workspaceId, conversationId, turns, retrievalSources, storageRestored]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns, stage, busy]);

  // 随空间切换拉取该空间引导问题（未配置时后端回退全局默认；自动模式直接拉全局默认）
  useEffect(() => {
    const url = workspaceId
      ? `/settings/workspaces/${workspaceId}/suggested-questions`
      : `/settings/suggested-questions`;
    api.get<{ questions: string[] }>(url)
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

  async function reloadHistory(id: string) {
    try {
      const hist = await api.get<ConversationHistory>(`/conversations/${id}`);
      setTurns(historyTurns(hist));
      const selection = hist.messages.findLast((message) => message.role === "user")?.retrieval?.retrieval_sources;
      if (selection) setRetrievalSources(selection);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("load_failed"));
    }
  }

  async function selectConversation(id: string) {
    // 切走前先断开上一条流（只退订，后台任务继续）
    abortRef.current?.abort();
    abortRef.current = null;
    reconnectFreshRef.current = false;
    setBusy(false);
    setStreamingText("");
    setStreamingThinking("");
    thinkingAccRef.current = "";
    setInterrupted(false);
    setError(null);
    setConversationId(id);
    await reloadHistory(id);
    // 若该会话仍在后台生成，重连实时流续看答案
    if (activeIds.has(id)) {
      setGenerationStartedAtMs(activeStartedAtById[id] ?? null);
      reconnectStream(id);
    }
  }

  function newConversation() {
    setConversationId(null);
    setTurns([]);
    setError(null);
    setInterrupted(false);
  }

  async function stopGeneration() {
    // 先请求后端取消生成任务，再断开本地流（对齐聊天+）
    if (conversationId) {
      try {
        await api.post(`/chat/stop/${conversationId}`, {});
      } catch { /* 不在跑 / 已结束：忽略 */ }
    }
    abortRef.current?.abort();
  }

  // 共用的 SSE 事件处理器（发送 + 重连共用）。reconnect=true 时首个流块先清空重建，
  // 避免 catchup 补发的完整内容与已有残留重复/留白。
  function makeStreamHandler() {
    return (event: string, data: unknown) => {
      const consumeReconnectFresh = () => {
        if (reconnectFreshRef.current) {
          reconnectFreshRef.current = false;
          return true;
        }
        return false;
      };
      if (event === "meta") {
        // 首发/重连都带 conversation_id：新会话在 done 之前断流也能重连
        const d = data as StreamMetaPayload;
        const anchor = startAnchorMs(d);
        if (anchor !== null) setGenerationStartedAtMs(anchor);
        setConversationId(d.conversation_id);
        setConversations((prev) => {
          if (prev.some((c) => c.id === d.conversation_id)) return prev;
          return [
            { id: d.conversation_id, workspace_id: workspaceId ?? "", title: null, pinned: false, created_at: new Date().toISOString() },
            ...prev,
          ];
        });
      } else if (event === "stage") {
        const { stage: sk, message_key, message_params, agent_runs } = data as {
          stage: string;
          message_key: string;
          message_params: Record<string, unknown>;
          agent_runs?: AgentRun[] | null;
        };
        setStageKey(sk);
        setStage(t(message_key, message_params as Record<string, string>));
        if (Array.isArray(agent_runs)) setAgentProgress(agent_runs);
      } else if (event === "thinking") {
        const text = (data as { text: string }).text;
        if (consumeReconnectFresh()) thinkingAccRef.current = "";
        thinkingAccRef.current += text;
        setStreamingThinking(thinkingAccRef.current);
      } else if (event === "token") {
        const text = (data as { text: string }).text;
        if (consumeReconnectFresh()) {
          setStreamingText(text);
        } else {
          setStreamingText((prev) => prev + text);
        }
      } else if (event === "done") {
        setStreamingText("");
        setStreamingThinking("");
        const savedThinking = thinkingAccRef.current || undefined;
        thinkingAccRef.current = "";
        const d = data as DonePayload;
        setConversationId(d.conversation_id);
        setTurns((prev) => {
          // 重连补发的 done 可能与已落库历史重复：末条已是同内容 assistant 则不重复追加
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.content === d.answer) return prev;
          return [
            ...prev,
            { role: "assistant", content: d.answer, sources: d.sources, error_key: d.error_key, thinking: savedThinking, agent_runs: d.agent_runs, warning: d.warning },
          ];
        });
        setBusy(false);
        setStage(null);
        setStageKey(null);
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
    };
  }

  // 重连正在后台运行的生成流。attempt=0 为首次（切回会话 / 首发 409）；>0 为断流后自动重连（退避）。
  async function reconnectStream(convId: string, attempt = 0) {
    if (attempt === 0) {
      setAgentProgress(null);
      setStageKey(null);
    }
    setError(null);
    if (activeStartedAtById[convId] !== undefined) {
      setGenerationStartedAtMs(activeStartedAtById[convId]);
    }
    setBusy(true);
    reconnectFreshRef.current = true;
    const ac = new AbortController();
    abortRef.current = ac;
    let finished = false;
    try {
      await api.streamGet(`/chat/stream/${convId}`, makeStreamHandler(), ac.signal);
      finished = true;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return; // 切走/停止：不报错，也不重连
      }
      if (err instanceof ApiError && err.status === 404) {
        // 生成已结束且过了保留窗口——拉历史显示最终结果，不报错
        await reloadHistory(convId);
        finished = true;
        return;
      }
      if (attempt < RECONNECT_BACKOFF_MS.length) {
        setError(t("reconnecting"));
        await sleep(RECONNECT_BACKOFF_MS[attempt]);
        if (ac.signal.aborted) return;
        await reconnectStream(convId, attempt + 1);
        return;
      }
      try {
        const r = await api.get<ActiveGenerationsResponse>("/chat/active");
        if (activeResponseIds(r).includes(convId)) {
          setError(t("reconnectPending"));
        } else {
          await reloadHistory(convId);
        }
      } catch {
        setError(t("reconnectFailed"));
      }
      finished = true;
    } finally {
      if (finished || attempt >= RECONNECT_BACKOFF_MS.length) {
        setBusy(false);
        setStage(null);
        setStageKey(null);
        setStreamingText("");
        setStreamingThinking("");
        thinkingAccRef.current = "";
        reconnectFreshRef.current = false;
        abortRef.current = null;
      }
    }
  }

  if (!ready) return null;

  // Before the server confirms its authorized registry, show selected sources as
  // queued. A server snapshot replaces these placeholders, including on reconnect.
  const progressAgents: AgentRun[] = agentProgress ?? retrievalSources.flatMap((source) => {
    const matching = availableAgents.filter((a) => a.source_type === source
      && (source !== "workspace" || !workspaceId || a.workspace_id === workspaceId));
    return matching.length ? matching.map((a) => ({
      agent_id: a.id, name: a.name, source_type: a.source_type, status: "queued",
    })) : [{ agent_id: source, name: t(`source_${source}`), source_type: source, status: "queued" }];
  });

  async function sendMessage(message: string, options: { replaceFrom?: number; retry?: boolean } = {}) {
    message = message.trim();
    if (!message || busy) return;
    // Every entry point records its question before sending. Retrying keeps the
    // existing user turn; editing replaces that turn and the responses after it.
    if (!options.retry) {
      setTurns((previous) => [
        ...(options.replaceFrom === undefined ? previous : previous.slice(0, options.replaceFrom)),
        { role: "user", content: message },
      ]);
    }
    setError(null);
    setInterrupted(false);
    setGenerationStartedAtMs(Date.now());
    setBusy(true);
    setAgentProgress(null);
    setStageKey(null);
    setStage(t("preparing"));

    const ac = new AbortController();
    abortRef.current = ac;
    reconnectFreshRef.current = false;

    // 标记答案（done）是否已到达：done 之后仍有落库/标题等收尾，此时断流不应误报失败
    let doneReceived = false;
    const handler = makeStreamHandler();
    try {
      await api.stream(
        "/chat/stream",
        {
          workspace_id: workspaceId,
          retrieval_sources: retrievalSources,
          message,
          conversation_id: conversationId,
        },
        (event, data) => {
          if (event === "done") doneReceived = true;
          handler(event, data);
        },
        ac.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return; // 切走/停止：任务后台继续，不报错也不收尾
      } else if (err instanceof ApiError && err.status === 409) {
        // 该会话已在生成（重复发送）：转为重连订阅正在跑的流
        const cid = conversationIdRef.current;
        if (cid) { await reconnectStream(cid); return; }
      } else if (!doneReceived) {
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
    if (!message || busy) return;
    setInput("");
    await sendMessage(message);
  }

  async function handleEdit(turnIndex: number, newContent: string) {
    await sendMessage(newContent, { replaceFrom: turnIndex });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(e as unknown as React.FormEvent);
    }
  }

  async function download(source: SourceRef) {
    if (!source.doc_id) return;
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

      {exportOpen && conversationId && (
        <ExportConversationModal
          conversationId={conversationId}
          conversationTitle={conversations.find((c) => c.id === conversationId)?.title ?? null}
          onClose={() => setExportOpen(false)}
        />
      )}

      <div className="flex flex-1 overflow-hidden">
        <ConversationSidebar
          collapseOnSmallScreens
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
                  agentRuns={turn.agent_runs}
                  errorKey={turn.error_key}
                  warning={turn.warning}
                  onDownload={download}
                  onEdit={turn.role === "user" && !busy ? (newContent) => handleEdit(i, newContent) : undefined}
                  onResend={interrupted && !busy && turn.role === "user" && i === turns.length - 1 ? () => sendMessage(turn.content, { retry: true }) : undefined}
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
                      <p className="mb-1 flex items-center gap-2 text-xs font-medium text-gray-400">
                        {t("thinking_label")}
                        <span className="font-mono tabular-nums">{elapsed}s</span>
                      </p>
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
            ) : busy && progressAgents.length > 0 ? (
              <AgentProgress agents={progressAgents} stageKey={stageKey} elapsed={elapsed} />
            ) : busy ? (
              <div className="flex items-center gap-2">
                <ThinkingBubble stage={stage} stageKey={stageKey} />
                <span className="font-mono tabular-nums text-xs text-gray-400">{elapsed}s</span>
              </div>
            ) : null}
          </div>

          {error && (
            <div className="mx-4 mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* Input area */}
          <div className="border-t border-gray-200 bg-white px-4 py-3">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <fieldset disabled={busy} aria-label={t("retrieval_sources")} className="flex min-w-0 flex-[1_1_40rem] flex-wrap items-center gap-2 text-xs disabled:opacity-60">
                <span className="text-gray-500">{t("retrieval_sources")}</span>
                {(["workspace", "paloalto_kb", "paloalto_live", "paloalto_docs"] as RetrievalSource[]).map((id) => {
                  const available = id === "workspace" || availableAgents.some((a) => a.id === id);
                  const selected = retrievalSources.includes(id);
                  return (
                    <label key={id} className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 ${selected ? "border-blue-200 bg-blue-50 text-blue-700" : "border-gray-200 text-gray-600"} ${available ? "cursor-pointer" : "opacity-50"}`}>
                      <input type="checkbox" checked={selected} disabled={!available && !selected}
                        onChange={() => setRetrievalSources((previous) => selected
                          ? previous.filter((value) => value !== id) : [...previous, id])}
                        className="accent-blue-600" />
                      {t(`source_${id}`)}
                    </label>
                  );
                })}
                <div className="flex items-center gap-2 sm:ml-2">
                  <span className="text-gray-500">{t("workspace_label")}</span>
                  <WorkspacePicker value={workspaceId} onChange={setWorkspaceId}
                    disabled={busy || !retrievalSources.includes("workspace")} ariaLabel={t("workspace_label")} />
                </div>
              </fieldset>
              {conversationId && (
                <button
                  onClick={() => setExportOpen(true)}
                  className="ml-auto flex shrink-0 items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                  {t("export")}
                </button>
              )}
            </div>
            {agentsError && <p className="mb-2 text-xs text-amber-700">{t("agents_load_failed")}</p>}
            {retrievalSources.length === 0 && <p className="mb-2 text-xs text-gray-500">{t("knowledge_only")}</p>}
            <form onSubmit={send}>
              <div className="flex items-end gap-3 rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-500 transition-all">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={t("ask_placeholder")}
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
                    title={t("stop_generating")}
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    </svg>
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim()}
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
