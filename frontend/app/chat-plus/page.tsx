"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import ConversationSidebar from "@/components/ConversationSidebar";
import ScheduledTaskPanel from "@/components/chat-plus/ScheduledTaskPanel";
import ExportConversationModal from "@/components/ExportConversationModal";
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

type StreamBlock =
  | { type: "thinking"; text: string }
  | { type: "text"; text: string };

const SESSION_KEY = "chat_plus_state";

// SSE 中断后自动重连：最多 3 次，退避 1s / 2s / 4s
const RECONNECT_BACKOFF_MS = [1000, 2000, 4000];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const epochSecondsToMs = (seconds: number) => Math.max(0, seconds * 1000);
// 由服务器「已运行秒数」反推一个基于本机时钟的起点锚点：
// 之后计时全程用 Date.now() - anchor（同一时钟），免疫客户端/服务端墙钟偏移。
// 无 elapsed_seconds 时回退到服务器绝对 started_at（旧后端兼容，可能有偏移）。
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
  const [activeStartedAtById, setActiveStartedAtById] = useState<Record<string, number>>({});
  const [generationStartedAtMs, setGenerationStartedAtMs] = useState<number | null>(null);
  // 首次 active 轮询已返回（驱动挂载重连 effect 重跑，含 activeIds 为空的 finished-while-away 场景）
  const [firstPollDone, setFirstPollDone] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [scheduledPanelOpen, setScheduledPanelOpen] = useState(false);

  // 是否有 skills:write（控制「存为 Skill」显隐；后端仍是唯一防线）
  const [canWriteSkill, setCanWriteSkill] = useState(false);
  // 是否有 documents:write（控制「保存到文档库」显隐；后端仍是唯一防线）
  const [canWriteDoc, setCanWriteDoc] = useState(false);

  // Chat+ extras
  const [activeSkillIds, setActiveSkillIds] = useState<string[]>([]);
  const [docFilterIds, setDocFilterIds] = useState<string[]>([]);
  const [allDocs, setAllDocs] = useState(false);
  // 交互模式：开时后端注入 ask-user 协议，模型可弹选项让用户澄清（瞬时，不持久化）
  const [interactive, setInteractive] = useState(false);
  // 引擎覆盖：空字符串 = 跟随系统默认；"claude_cli" / "codex" = 本轮强制指定
  const [engineOverride, setEngineOverride] = useState<"" | "claude_cli" | "codex">("");
  // 读取原始文件：开时把引用文档的原始文件拷进工作目录供 Claude 读全文（瞬时，不持久化）
  const [useOriginalDocs, setUseOriginalDocs] = useState(false);
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
  // 重连模式：收到重连流首个 thinking/token 时先清空一次再累积（幂等重建，避免留白/重复）
  const reconnectFreshRef = useRef(false);
  // 追踪最新 conversation_id，供异步 catch 读取（新会话经 meta 事件中途才知晓）
  const conversationIdRef = useRef<string | null>(null);
  // 从 sessionStorage 恢复出的会话正处于「生成中」快照——用于挂载后判定是否需重连
  const restoredBusyConvRef = useRef<string | null>(null);
  // 首次 /chat/plus/active 轮询是否已返回（重连判定须等它，避免误判 finished-while-away）
  const firstPollDoneRef = useRef(false);
  // 挂载恢复是否已完成：持久化 effect 必须等它为 true 才写 sessionStorage，
  // 否则 mount 首帧（streamingBlocks 尚为初始 []）会用空值覆写掉刚要恢复的快照。
  const restoredRef = useRef(false);

  useEffect(() => {
    // 会话不分空间：仅从 sessionStorage 恢复该窗口的当前对话/消息。
    // 工作区是每轮瞬时上下文，不持久化、不影响会话列表。
    // 进行中的 streamingBlocks/busy/generationStartedAtMs 也一并恢复，
    // 保证用户切换菜单再返回时能立即看到离开时的 thinking 内容（不依赖后端 catchup）。
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        const s = JSON.parse(raw) as {
          conversationId: string | null;
          turns: Turn[];
          streamingBlocks?: StreamBlock[];
          busy?: boolean;
          generationStartedAtMs?: number | null;
        };
        setConversationId(s.conversationId);
        setTurns(s.turns);
        if (s.streamingBlocks && s.streamingBlocks.length > 0) {
          setStreamingBlocks(s.streamingBlocks);
          streamingBlocksRef.current = s.streamingBlocks;
        }
        if (s.busy) {
          setBusy(true);
          // 恢复锚点：优先用缓存值；否则从现在起算（后续 active 查询/重连会校正）
          setGenerationStartedAtMs(s.generationStartedAtMs ?? Date.now());
          // 记下「恢复即生成中」的会话，挂载后据此重连（无论是否仍在 active——
          // 若已在 grace 窗口内结束，reconnectStream 会补发 done；过窗口则 404→拉历史）
          restoredBusyConvRef.current = s.conversationId;
        }
      }
    } catch {}
  }, []);

  // unmount：仅断开本地 SSE 订阅（后端生成继续跑）。取消生成只走「停止」按钮。
  useEffect(() => { return () => { abortRef.current?.abort(); }; }, []);

  // 拉取权限，决定是否显示「存为 Skill」/「保存到文档库」（admin 恒可）
  useEffect(() => {
    if (isAdmin()) {
      setCanWriteSkill(true);
      setCanWriteDoc(true);
      return;
    }
    api
      .get<Record<string, string>>("/auth/my-permissions")
      .then((perms) => {
        setCanWriteSkill(perms.skills === "write");
        setCanWriteDoc(perms.documents === "write");
      })
      .catch(() => {
        setCanWriteSkill(false);
        setCanWriteDoc(false);
      });
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
        const r = await api.get<ActiveGenerationsResponse>("/chat/plus/active");
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
        // 首次轮询完成后翻一次标志，驱动挂载重连 effect 重跑（即使 activeIds 仍为空，
        // 也需据此判定 finished-while-away：恢复的 busy 会话要重连一次以拉最终结果/清 busy）
        if (!cancelled && !firstPollDoneRef.current) {
          firstPollDoneRef.current = true;
          setFirstPollDone(true);
        }
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    conversationIdRef.current = conversationId;
    // 跳过 mount 首次执行：此时恢复 effect 的 setState 尚未生效，streamingBlocks 仍是
    // 初始 []，若此刻写入会用空值覆写掉 sessionStorage 里刚要恢复的快照。
    if (!restoredRef.current) {
      restoredRef.current = true;
      return;
    }
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        conversationId,
        turns,
        streamingBlocks,
        busy,
        generationStartedAtMs,
      }));
    } catch {}
  }, [conversationId, turns, streamingBlocks, busy, generationStartedAtMs]);

  // 同标签页返回：等首次 active 轮询返回后再判定（依赖 [firstPollDone] 重跑，
  // 避免 [] 依赖读到恢复前的 stale 闭包值导致 conversationId=null、重连永不触发）。
  // 恢复的「生成中」会话一律重连一次：仍在跑→接回 catchup 续看；grace 窗口内已结束
  // →补发 done；过窗口→404 拉历史。闸门用 !abortRef.current（未在流中）而非 !busy，
  // 因恢复时可能已 setBusy(true)，用 busy 会把重连卡死。
  useEffect(() => {
    if (mountReconnectDoneRef.current) return;
    if (!firstPollDone) return;
    mountReconnectDoneRef.current = true;
    const cid = conversationId ?? restoredBusyConvRef.current;
    if (!cid || abortRef.current) return;
    // 仅当该会话仍在后台生成，或本次是从「生成中」快照恢复的会话，才重连
    if (activeIds.has(cid) || restoredBusyConvRef.current === cid) {
      setGenerationStartedAtMs(activeStartedAtById[cid] ?? null);
      reconnectStream(cid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstPollDone]);

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

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  async function selectConversation(id: string) {
    // 切走前先断开上一条流并清理，避免两条流叠加 / 上一会话的流块串到新会话
    abortRef.current?.abort();
    abortRef.current = null;
    reconnectFreshRef.current = false;
    setBusy(false);
    setStreamingBlocks([]);
    streamingBlocksRef.current = [];
    setError(null);
    setConversationId(id);
    setAttachedFiles([]);
    // 切换会话：工作区/文档是瞬时上下文，一律重置为「不引用」
    setWorkspaceId(null);
    setDocFilterIds([]);
    setAllDocs(false);
    setUseOriginalDocs(false);
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
      setGenerationStartedAtMs(activeStartedAtById[id] ?? null);
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
    setUseOriginalDocs(false);
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
    // 重连后收到的首个流块要触发一次「幂等重建」（清空再按 catchup 累积），只消费一次
    const consumeReconnectFresh = () => {
      if (reconnectFreshRef.current) {
        reconnectFreshRef.current = false;
        return true;
      }
      return false;
    };
    return (event: string, data: unknown) => {
      // 聊天+ 不再展示三步动画，忽略 stage 事件
      if (event === "meta") {
        // 首发事件带 conversation_id：新会话在 done 之前断流也能重连
        const d = data as StreamMetaPayload;
        const anchor = startAnchorMs(d);
        if (anchor !== null) {
          setGenerationStartedAtMs(anchor);
        }
        setConversationId(d.conversation_id);
        setConversations((prev) => {
          if (prev.some((c) => c.id === d.conversation_id)) return prev;
          return [
            { id: d.conversation_id, workspace_id: null, title: null, pinned: false, created_at: new Date().toISOString() },
            ...prev,
          ];
        });
      } else if (event === "thinking") {
        const text = (data as { text: string }).text;
        setStreamingBlocks((prev) => {
          // 重连后首个流块：清空一次再累积（catchup 会按序补发完整内容，避免重复/留白）
          const base = consumeReconnectFresh() ? [] : prev;
          const last = base[base.length - 1];
          const next = last?.type === "thinking"
            ? [...base.slice(0, -1), { type: "thinking" as const, text: last.text + text }]
            : [...base, { type: "thinking" as const, text }];
          streamingBlocksRef.current = next;
          return next;
        });
      } else if (event === "token") {
        const text = (data as { text: string }).text;
        setStreamingBlocks((prev) => {
          const base = consumeReconnectFresh() ? [] : prev;
          const last = base[base.length - 1];
          const next = last?.type === "text"
            ? [...base.slice(0, -1), { type: "text" as const, text: last.text + text }]
            : [...base, { type: "text" as const, text }];
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

  // 生成已结束且过了保留窗口（重连 404）：静默拉取历史，显示最终结果。
  async function reloadHistory(convId: string) {
    try {
      const hist = await api.get<ConversationHistory>(`/conversations/${convId}`);
      setTurns(
        hist.messages.map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources,
          attachments: m.attachments ?? [],
          output_files: m.output_files ?? [],
        }))
      );
    } catch {
      /* 拉历史失败也不打断：保持已渲染内容 */
    }
  }

  // 重连正在后台运行的生成流。
  // attempt=0 为首次（切回会话 / 首发 409）；>0 为断流后的自动重连（带退避）。
  // 断流不再直接报「失败」：只要后端仍在跑就自动接回，Thinking 由 catchup 连续补发。
  async function reconnectStream(convId: string, attempt = 0) {
    setError(null);
    if (activeStartedAtById[convId] !== undefined) {
      setGenerationStartedAtMs(activeStartedAtById[convId]);
    }
    setBusy(true);
    setPendingOutputFiles([]);
    // 不在此清空 streamingBlocks（避免留白）；改由 handler 收到首个流块时幂等重建
    reconnectFreshRef.current = true;
    const ac = new AbortController();
    abortRef.current = ac;
    let finished = false;
    try {
      await api.streamGet(
        `/chat/plus/stream/${convId}`,
        makeStreamHandler(false),
        ac.signal,
      );
      finished = true; // 流正常结束（done 事件已处理）
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
      // 其它中断：后端任务可能仍在跑，自动退避重连
      if (attempt < RECONNECT_BACKOFF_MS.length) {
        setError(t("reconnecting"));
        await sleep(RECONNECT_BACKOFF_MS[attempt]);
        if (ac.signal.aborted) return; // 退避期间被切走/停止
        await reconnectStream(convId, attempt + 1);
        return;
      }
      // 重试用尽：确认后端是否仍在跑
      try {
        const r = await api.get<ActiveGenerationsResponse>("/chat/plus/active");
        if (activeResponseIds(r).includes(convId)) {
          // 仍在跑，但连不上：提示可稍后切回，不误报致命失败
          setError(t("reconnectPending"));
        } else {
          // 已不在跑：拉历史看结果
          await reloadHistory(convId);
        }
      } catch {
        setError(t("reconnectFailed"));
      }
      finished = true;
    } finally {
      // 仅在本次不再继续重连（正常结束 / 放弃）时收尾，避免中途 finally 清空转圈
      if (finished || attempt >= RECONNECT_BACKOFF_MS.length) {
        setBusy(false);
        setStreamingBlocks([]);
        streamingBlocksRef.current = [];
        reconnectFreshRef.current = false;
        abortRef.current = null;
      }
    }
  }

  async function sendMessage(message: string, currentAttachments?: AttachedFile[]) {
    if (!message || busy) return;
    setError(null);
    setGenerationStartedAtMs(Date.now());
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
          use_original_docs: useOriginalDocs,
          interactive,
          engine_override: engineOverride || undefined,
          attachments: filesToSend.length > 0 ? filesToSend : null,
        },
        makeStreamHandler(isNew),
        ac.signal,
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // 切走/停止：直接 return，跳过 finally 的清空，保留 streamingBlocks 快照
        // （持久化 effect 会把非空快照写回 sessionStorage，返回时可立即看到 thinking）
        return;
      } else if (err instanceof ApiError && err.status === 409 && conversationId) {
        // 该会话已有生成在跑（重复发送）：透明切换为订阅同一路流
        setAttachedFiles([]);
        abortRef.current = null;
        await reconnectStream(conversationId);
        return;
      } else {
        // 区分「发起就失败」与「生成中途断流」：
        // convId 已知（含本轮 meta 事件中途学到的）说明生成已启动，属可恢复的断流 → 自动重连；
        // 否则是尚未开始生成的真失败 → 提示 requestFailed。
        const convId = conversationIdRef.current;
        const recoverable =
          convId !== null && !(err instanceof ApiError && err.status >= 400 && err.status < 500);
        if (recoverable) {
          setAttachedFiles([]);
          abortRef.current = null;
          await reconnectStream(convId!);
          return;
        }
        setError(err instanceof ApiError ? err.message : t("requestFailed"));
      }
    } finally {
      // 切走(abort)时保留 streamingBlocks 快照，让持久化 effect 落非空快照供返回时恢复；
      // 仅在正常结束/真失败时清空。
      if (!ac.signal.aborted) {
        setBusy(false);
        setStreamingBlocks([]);
        streamingBlocksRef.current = [];
        abortRef.current = null;
        setAttachedFiles([]);
      }
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

  async function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(e.clipboardData.files);
    if (files.length === 0) return;
    e.preventDefault();
    const results: AttachedFile[] = [];
    for (const file of files) {
      try {
        const form = new FormData();
        form.append("file", file);
        const r = await api.upload<AttachedFile>("/chat/plus/upload", form);
        results.push(r);
      } catch {
        // 单文件失败不中断其余
      }
    }
    if (results.length > 0) setAttachedFiles((prev) => [...prev, ...results]);
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
          onScheduledTasks={() => setScheduledPanelOpen(true)}
        />
        <ScheduledTaskPanel
          open={scheduledPanelOpen}
          onClose={() => setScheduledPanelOpen(false)}
          onRun={loadConversations}
        />

        <main className="flex flex-1 flex-col overflow-hidden">
          {conversationId && (
            <div className="flex items-center justify-end border-b border-gray-100 bg-white px-4 py-1.5">
              <button
                onClick={() => setExportOpen(true)}
                className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 transition-colors"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
                {t("export")}
              </button>
            </div>
          )}
          {exportOpen && conversationId && (
            <ExportConversationModal
              conversationId={conversationId}
              conversationTitle={conversations.find((c) => c.id === conversationId)?.title ?? null}
              onClose={() => setExportOpen(false)}
            />
          )}
          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
            {turns.length === 0 && !busy && (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-purple-100 text-purple-600">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4Q13 11 20 12Q13 13 12 20Q11 13 4 12Q11 11 12 4z" />
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
                      {t("thinkingProcess")}
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
                    <OutputFileChip files={turn.output_files} conversationId={conversationId} canWriteSkill={canWriteSkill} canWriteDoc={canWriteDoc} />
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
                useOriginal={useOriginalDocs}
                onUseOriginalChange={setUseOriginalDocs}
              />
              <FileAttachPanel files={attachedFiles} onChange={setAttachedFiles} />
              <SessionFilesPanel ref={sessionFilesRef} conversationId={conversationId} canWriteSkill={canWriteSkill} canWriteDoc={canWriteDoc} />
              <button
                type="button"
                onClick={() => setInteractive((v) => !v)}
                title={t("interactiveModeTitle")}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
                  interactive
                    ? "border-purple-400 bg-purple-50 text-purple-700"
                    : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                <span
                  className={`h-2 w-2 rounded-full ${interactive ? "bg-purple-500" : "bg-gray-300"}`}
                />
                {t("interactiveMode")}
              </button>
              <select
                value={engineOverride}
                onChange={(e) => setEngineOverride(e.target.value as "" | "claude_cli" | "codex")}
                title={t("engineOverrideTitle")}
                className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-600 focus:border-purple-400 focus:outline-none"
              >
                <option value="">{t("engineOverrideDefault")}</option>
                <option value="claude_cli">Claude CLI</option>
                <option value="codex">Codex CLI</option>
              </select>
            </div>

            <form onSubmit={send}>
              <div className="flex items-end gap-3 rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 focus-within:border-purple-500 focus-within:ring-1 focus-within:ring-purple-500 transition-all">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onPaste={handlePaste}
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
