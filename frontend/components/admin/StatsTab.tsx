"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "@/components/IntlProvider";
import { toDateLocale } from "@/lib/locale";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";

interface DailyAction {
  day: string;
  action: string;
  count: number;
}
interface DailyActiveUser {
  day: string;
  users: number;
}
interface PerUser {
  email: string;
  login: number;
  upload: number;
  chat: number;
  download: number;
  total: number;
}
interface Stats {
  days: number;
  daily: DailyAction[];
  active_users: DailyActiveUser[];
  totals: Record<string, number>;
  per_user: PerUser[];
}
interface LogFile {
  name: string;
  size: number;
  mtime: number;
}

const ACTION_COLORS: Record<string, string> = {
  login: "#3b82f6",
  upload: "#10b981",
  chat: "#f59e0b",
  download: "#8b5cf6",
};
const DAY_OPTIONS = [7, 14, 30, 90, 180, 365];

// ── 柱图 ──────────────────────────────────────────────

function MiniBarChart({
  data,
  color,
}: {
  data: { day: string; count: number }[];
  color: string;
}) {
  const t = useTranslations("stats");
  if (data.length === 0) return <p className="text-xs text-gray-400">{t("no_data")}</p>;
  const max = Math.max(...data.map((d) => d.count), 1);
  const W = 400;
  const H = 80;
  const pad = 4;
  const slot = (W - pad * 2) / data.length;
  const barW = Math.max(1, Math.floor(slot * 0.7));

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
      {data.map((d, i) => {
        const bh = Math.max(2, Math.round((d.count / max) * (H - 18)));
        const x = pad + i * slot + (slot - barW) / 2;
        const y = H - bh - 14;
        return (
          <g key={d.day}>
            <rect x={x} y={y} width={barW} height={bh} fill={color} rx={1} opacity={0.85}>
              <title>{d.day}: {d.count}</title>
            </rect>
          </g>
        );
      })}
      {data.length > 0 && (
        <>
          <text x={pad} y={H} fontSize={9} fill="#9ca3af">{data[0].day.slice(5)}</text>
          <text x={W - pad - 28} y={H} fontSize={9} fill="#9ca3af">
            {data[data.length - 1].day.slice(5)}
          </text>
        </>
      )}
    </svg>
  );
}

// ── 折线图 ────────────────────────────────────────────

function ActiveUsersChart({ data }: { data: DailyActiveUser[] }) {
  const t = useTranslations("stats");
  if (data.length === 0) return <p className="text-xs text-gray-400">{t("no_data")}</p>;
  const max = Math.max(...data.map((d) => d.users), 1);
  const W = 400;
  const H = 80;
  const pad = 4;

  const pts = data.map((d, i) => {
    const x = pad + (i / Math.max(data.length - 1, 1)) * (W - pad * 2);
    const y = H - 14 - (d.users / max) * (H - 20);
    return `${x},${y}`;
  });

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
      <polyline points={pts.join(" ")} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
      {data.map((d, i) => {
        const x = pad + (i / Math.max(data.length - 1, 1)) * (W - pad * 2);
        const y = H - 14 - (d.users / max) * (H - 20);
        return (
          <circle key={d.day} cx={x} cy={y} r={2.5} fill="#3b82f6">
            <title>{d.day}: {d.users}</title>
          </circle>
        );
      })}
      {data.length > 0 && (
        <>
          <text x={pad} y={H} fontSize={9} fill="#9ca3af">{data[0].day.slice(5)}</text>
          <text x={W - pad - 28} y={H} fontSize={9} fill="#9ca3af">
            {data[data.length - 1].day.slice(5)}
          </text>
        </>
      )}
    </svg>
  );
}

// ── 日志查看面板 ──────────────────────────────────────

function LogViewer() {
  const t = useTranslations("stats");
  const [files, setFiles] = useState<LogFile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [lines, setLines] = useState(500);
  const [content, setContent] = useState<string | null>(null);
  const [logError, setLogError] = useState<string | null>(null);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const textRef = useRef<HTMLPreElement>(null);

  const loadFiles = useCallback(async () => {
    setLoadingFiles(true);
    try {
      const f = await api.get<LogFile[]>("/admin/logs");
      setFiles(f);
      if (f.length > 0 && !selected) {
        const preferred = f.find((x) => x.name === "kb-agent.log") ?? f[0];
        setSelected(preferred.name);
      }
    } catch (err) {
      setLogError(err instanceof ApiError ? err.message : t("log_list_failed"));
    } finally {
      setLoadingFiles(false);
    }
  }, [selected, t]);

  const loadContent = useCallback(async (name: string, n: number) => {
    setLoadingContent(true);
    setLogError(null);
    try {
      const token = getToken();
      const res = await fetch(`/api/admin/logs/${encodeURIComponent(name)}?lines=${n}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d?.detail ?? `请求失败 (${res.status})`);
      }
      setContent(await res.text());
      setTimeout(() => {
        if (textRef.current) textRef.current.scrollTop = textRef.current.scrollHeight;
      }, 50);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : t("log_load_failed"));
    } finally {
      setLoadingContent(false);
    }
  }, [t]);

  useEffect(() => { loadFiles(); }, [loadFiles]);
  useEffect(() => {
    if (selected) loadContent(selected, lines);
  }, [selected, lines, loadContent]);

  function fmtSize(b: number) {
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 / 1024).toFixed(1)} MB`;
  }

  return (
    <div className="space-y-3">
      {/* 文件列表 + 行数选择 */}
      <div className="flex flex-wrap items-center gap-3">
        {loadingFiles ? (
          <span className="text-xs text-gray-400">{t("log_loading")}</span>
        ) : files.length === 0 ? (
          <span className="text-xs text-gray-400">
            {t("log_no_files")}
          </span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {files.map((f) => (
              <button
                key={f.name}
                onClick={() => setSelected(f.name)}
                className={`rounded border px-3 py-1 text-xs ${
                  selected === f.name
                    ? "border-blue-500 bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                {f.name}
                <span className="ml-1 text-gray-400">({fmtSize(f.size)})</span>
              </button>
            ))}
          </div>
        )}
        <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
          <span>{t("log_tail")}</span>
          {[200, 500, 1000, 2000].map((n) => (
            <button
              key={n}
              onClick={() => setLines(n)}
              className={`rounded px-2 py-0.5 ${
                lines === n ? "bg-blue-600 text-white" : "border hover:bg-gray-100"
              }`}
            >
              {t("log_lines", { n })}
            </button>
          ))}
          {selected && (
            <button
              onClick={() => selected && loadContent(selected, lines)}
              className="rounded border px-2 py-0.5 hover:bg-gray-100"
            >
              {t("log_refresh")}
            </button>
          )}
        </div>
      </div>

      {logError && <p className="text-xs text-red-600">{logError}</p>}

      {/* 日志内容 */}
      <pre
        ref={textRef}
        className="h-96 overflow-auto rounded border bg-gray-950 p-3 font-mono text-xs leading-relaxed text-gray-200"
      >
        {loadingContent ? (
          <span className="text-gray-500">{t("log_loading_content")}</span>
        ) : content === null ? (
          <span className="text-gray-500">{t("log_select_hint")}</span>
        ) : content.length === 0 ? (
          <span className="text-gray-500">{t("log_empty")}</span>
        ) : (
          content
        )}
      </pre>
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────

interface DownloadItem {
  created_at: string;
  email: string;
  document_id: string;
  document_title: string;
}
interface DownloadList { total: number; items: DownloadItem[]; }

interface ChatItem {
  created_at: string;
  email: string;
  conversation_id: string;
  question: string;
  answer: string;
}
interface ChatList { total: number; items: ChatItem[]; }

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export default function StatsTab() {
  const t = useTranslations("stats");
  const tc = useTranslations("common");
  const { locale } = useLocale();
  const dateLocale = toDateLocale(locale);

  function fmtTime(iso: string) {
    return new Date(iso).toLocaleString(dateLocale, { hour12: false });
  }

  const ACTION_LABELS: Record<string, string> = {
    login: t("action_login"),
    upload: t("action_upload"),
    chat: t("action_chat"),
    download: t("action_download"),
  };
  const ACTION_VOL_LABELS: Record<string, string> = {
    login: t("action_login_vol"),
    upload: t("action_upload_vol"),
    chat: t("action_chat_vol"),
    download: t("action_download_vol"),
  };

  const [innerTab, setInnerTab] = useState<"stats" | "downloads" | "chats" | "logs">("stats");
  const [stats, setStats] = useState<Stats | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [dlData, setDlData] = useState<DownloadList | null>(null);
  const [dlPage, setDlPage] = useState(1);
  const [dlLoading, setDlLoading] = useState(false);

  const [chatData, setChatData] = useState<ChatList | null>(null);
  const [chatPage, setChatPage] = useState(1);
  const [chatLoading, setChatLoading] = useState(false);
  const [expandedChat, setExpandedChat] = useState<string | null>(null);

  const loadDownloads = useCallback(async (d: number, page: number) => {
    setDlLoading(true);
    try {
      setDlData(await api.get<DownloadList>(`/admin/usage/downloads?days=${d}&page=${page}&page_size=50`));
    } catch { /* ignore */ } finally { setDlLoading(false); }
  }, []);

  const loadChats = useCallback(async (d: number, page: number) => {
    setChatLoading(true);
    try {
      setChatData(await api.get<ChatList>(`/admin/usage/chats?days=${d}&page=${page}&page_size=50`));
    } catch { /* ignore */ } finally { setChatLoading(false); }
  }, []);

  const load = useCallback(async (d: number) => {
    setLoading(true);
    setError(null);
    try {
      setStats(await api.get<Stats>(`/admin/stats?days=${d}`));
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 500)) {
        setError(
          "报表数据不可用。请确认已执行数据库迁移：\n./scripts/dev.sh  （或手动执行 infra/postgres/migrations/009_usage_events.sql）"
        );
      } else {
        setError(err instanceof ApiError ? err.message : t("load_failed"));
      }
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (innerTab === "stats") load(days);
    if (innerTab === "downloads") loadDownloads(days, dlPage);
    if (innerTab === "chats") loadChats(days, chatPage);
  }, [days, load, loadDownloads, loadChats, innerTab, dlPage, chatPage]);

  function byAction(action: string) {
    const map: Record<string, number> = {};
    (stats?.daily ?? [])
      .filter((d) => d.action === action)
      .forEach((d) => { map[d.day] = (map[d.day] ?? 0) + d.count; });
    const days_list = stats?.active_users.map((d) => d.day) ?? Object.keys(map).sort();
    return days_list.map((day) => ({ day, count: map[day] ?? 0 }));
  }

  const actions = Object.keys(ACTION_LABELS);

  return (
    <div className="space-y-4">
      {/* 子 Tab */}
      <div className="flex gap-1 border-b">
        {([
          ["stats", t("tab_stats")],
          ["downloads", t("tab_downloads")],
          ["chats", t("tab_chats")],
          ["logs", t("tab_logs")],
        ] as const).map(([tabKey, label]) => (
          <button
            key={tabKey}
            onClick={() => {
              setInnerTab(tabKey);
              if (tabKey === "downloads") setDlPage(1);
              if (tabKey === "chats") { setChatPage(1); setExpandedChat(null); }
            }}
            className={`px-4 py-2 text-sm ${
              innerTab === tabKey
                ? "border-b-2 border-blue-600 font-medium text-blue-700"
                : "text-gray-500 hover:text-gray-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── 报表 ── */}
      {innerTab === "stats" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-600">{t("time_range")}</span>
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded px-3 py-1 text-sm ${
                  days === d
                    ? "bg-blue-600 text-white"
                    : "border text-gray-600 hover:bg-gray-100"
                }`}
              >
                {tc("days_range", { days: d })}
              </button>
            ))}
            {loading && <span className="text-xs text-gray-400">{t("loading")}</span>}
          </div>

          {error && (
            <pre className="whitespace-pre-wrap rounded bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </pre>
          )}

          {!error && (
            <>
              {/* 汇总卡片 */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {actions.map((a) => (
                  <div key={a} className="rounded border bg-white p-4 text-center">
                    <p className="text-2xl font-bold" style={{ color: ACTION_COLORS[a] }}>
                      {stats?.totals[a] ?? "—"}
                    </p>
                    <p className="mt-1 text-xs text-gray-500">{ACTION_LABELS[a]}</p>
                  </div>
                ))}
              </div>

              {/* 活跃用户折线 */}
              <div className="rounded border bg-white p-4">
                <h3 className="mb-3 text-sm font-medium">{t("trend_title")}</h3>
                <ActiveUsersChart data={stats?.active_users ?? []} />
              </div>

              {/* 各动作柱图 */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {actions.map((a) => (
                  <div key={a} className="rounded border bg-white p-4">
                    <h3 className="mb-3 text-sm font-medium">{ACTION_VOL_LABELS[a]}</h3>
                    <MiniBarChart data={byAction(a)} color={ACTION_COLORS[a]} />
                  </div>
                ))}
              </div>

              {/* 用户明细表 */}
              <div className="rounded border bg-white">
                <div className="border-b px-4 py-3">
                  <h3 className="text-sm font-medium">{t("user_detail")}</h3>
                </div>
                {(stats?.per_user ?? []).length === 0 ? (
                  <p className="px-4 py-6 text-center text-sm text-gray-400">{t("no_data")}</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 text-xs text-gray-500">
                        <tr>
                          <th className="px-4 py-2 text-left">{t("col_user")}</th>
                          <th className="px-4 py-2 text-right">{t("col_login")}</th>
                          <th className="px-4 py-2 text-right">{t("col_upload")}</th>
                          <th className="px-4 py-2 text-right">{t("col_chat")}</th>
                          <th className="px-4 py-2 text-right">{t("col_download")}</th>
                          <th className="px-4 py-2 text-right font-semibold">{t("col_total")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {(stats?.per_user ?? []).map((u) => (
                          <tr key={u.email} className="hover:bg-gray-50">
                            <td className="px-4 py-2 font-mono text-xs">{u.email}</td>
                            <td className="px-4 py-2 text-right tabular-nums">{u.login || "—"}</td>
                            <td className="px-4 py-2 text-right tabular-nums">{u.upload || "—"}</td>
                            <td className="px-4 py-2 text-right tabular-nums">{u.chat || "—"}</td>
                            <td className="px-4 py-2 text-right tabular-nums">{u.download || "—"}</td>
                            <td className="px-4 py-2 text-right font-semibold tabular-nums">{u.total}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── 下载记录 ── */}
      {innerTab === "downloads" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-600">{t("time_range")}</span>
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => { setDays(d); setDlPage(1); }}
                className={`rounded px-3 py-1 text-sm ${
                  days === d ? "bg-blue-600 text-white" : "border text-gray-600 hover:bg-gray-100"
                }`}
              >
                {tc("days_range", { days: d })}
              </button>
            ))}
            {dlLoading && <span className="text-xs text-gray-400">{t("loading")}</span>}
          </div>
          <div className="rounded border bg-white">
            <div className="border-b px-4 py-3 flex items-center justify-between">
              <h3 className="text-sm font-medium">{t("download_records")}</h3>
              {dlData && <span className="text-xs text-gray-400">{tc("total_count", { count: dlData.total })}</span>}
            </div>
            {!dlData || dlData.items.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-gray-400">
                {dlLoading ? t("loading") : t("no_downloads")}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs text-gray-500">
                    <tr>
                      <th className="px-4 py-2 text-left">{t("col_time")}</th>
                      <th className="px-4 py-2 text-left">{t("col_email")}</th>
                      <th className="px-4 py-2 text-left">{t("col_doc")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {dlData.items.map((item, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-4 py-2 text-xs text-gray-500 whitespace-nowrap">{fmtTime(item.created_at)}</td>
                        <td className="px-4 py-2 font-mono text-xs">{item.email}</td>
                        <td className={`px-4 py-2 text-xs ${!item.document_title || item.document_title === t("deleted_doc") ? "text-gray-400 italic" : ""}`}>
                          {item.document_title}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {dlData && dlData.total > 50 && (
              <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-gray-500">
                <span>{tc("page_of", { page: dlPage, total: Math.ceil(dlData.total / 50) })}</span>
                <div className="flex gap-2">
                  <button
                    disabled={dlPage <= 1}
                    onClick={() => setDlPage((p) => p - 1)}
                    className="rounded border px-2 py-1 disabled:opacity-40 hover:bg-gray-100"
                  >
                    {tc("prev_page")}
                  </button>
                  <button
                    disabled={dlPage >= Math.ceil(dlData.total / 50)}
                    onClick={() => setDlPage((p) => p + 1)}
                    className="rounded border px-2 py-1 disabled:opacity-40 hover:bg-gray-100"
                  >
                    {tc("next_page")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 对话记录 ── */}
      {innerTab === "chats" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-600">{t("time_range")}</span>
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => { setDays(d); setChatPage(1); }}
                className={`rounded px-3 py-1 text-sm ${
                  days === d ? "bg-blue-600 text-white" : "border text-gray-600 hover:bg-gray-100"
                }`}
              >
                {tc("days_range", { days: d })}
              </button>
            ))}
            {chatLoading && <span className="text-xs text-gray-400">{t("loading")}</span>}
          </div>
          <div className="rounded border bg-white">
            <div className="border-b px-4 py-3 flex items-center justify-between">
              <h3 className="text-sm font-medium">{t("chat_records")}</h3>
              {chatData && <span className="text-xs text-gray-400">{tc("total_count", { count: chatData.total })}</span>}
            </div>
            {!chatData || chatData.items.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-gray-400">
                {chatLoading ? t("loading") : t("no_chats")}
              </p>
            ) : (
              <div className="divide-y">
                {chatData.items.map((item, i) => {
                  const key = `${item.conversation_id}-${i}`;
                  const expanded = expandedChat === key;
                  return (
                    <div
                      key={key}
                      className="px-4 py-3 hover:bg-gray-50 cursor-pointer"
                      onClick={() => setExpandedChat(expanded ? null : key)}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs text-gray-400 whitespace-nowrap">{fmtTime(item.created_at)}</span>
                            <span className="font-mono text-xs text-gray-600">{item.email}</span>
                          </div>
                          {expanded ? (
                            <div className="space-y-2 text-xs">
                              <div>
                                <span className="font-medium text-gray-700">{t("question")}</span>
                                <span className="text-gray-800 whitespace-pre-wrap">{item.question}</span>
                              </div>
                              <div>
                                <span className="font-medium text-gray-700">{t("answer")}</span>
                                <span className="text-gray-600 whitespace-pre-wrap">{item.answer}</span>
                              </div>
                            </div>
                          ) : (
                            <div className="text-xs text-gray-700">
                              <span className="font-medium">{t("q_abbr")}</span>{truncate(item.question, 80)}
                              {item.answer && (
                                <span className="ml-2 text-gray-400">
                                  <span className="font-medium">{t("a_abbr")}</span>{truncate(item.answer, 100)}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        <span className="text-xs text-gray-400 shrink-0">{expanded ? "▲" : "▼"}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            {chatData && chatData.total > 50 && (
              <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-gray-500">
                <span>{tc("page_of", { page: chatPage, total: Math.ceil(chatData.total / 50) })}</span>
                <div className="flex gap-2">
                  <button
                    disabled={chatPage <= 1}
                    onClick={() => setChatPage((p) => p - 1)}
                    className="rounded border px-2 py-1 disabled:opacity-40 hover:bg-gray-100"
                  >
                    {tc("prev_page")}
                  </button>
                  <button
                    disabled={chatPage >= Math.ceil(chatData.total / 50)}
                    onClick={() => setChatPage((p) => p + 1)}
                    className="rounded border px-2 py-1 disabled:opacity-40 hover:bg-gray-100"
                  >
                    {tc("next_page")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 日志 ── */}
      {innerTab === "logs" && <LogViewer />}
    </div>
  );
}
