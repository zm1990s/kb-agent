"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

const ACTION_LABELS: Record<string, string> = {
  login: "登录",
  upload: "上传",
  chat: "对话",
  download: "下载",
};
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
  if (data.length === 0) return <p className="text-xs text-gray-400">暂无数据</p>;
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
  if (data.length === 0) return <p className="text-xs text-gray-400">暂无数据</p>;
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
            <title>{d.day}: {d.users} 人</title>
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
      setLogError(err instanceof ApiError ? err.message : "获取日志列表失败");
    } finally {
      setLoadingFiles(false);
    }
  }, [selected]);

  const loadContent = useCallback(async (name: string, n: number) => {
    setLoadingContent(true);
    setLogError(null);
    try {
      // read log as plain text via api.get (returns undefined for non-JSON) — use fetch directly
      const token = getToken();
      const res = await fetch(`/api/admin/logs/${encodeURIComponent(name)}?lines=${n}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d?.detail ?? `请求失败 (${res.status})`);
      }
      setContent(await res.text());
      // 滚到底部
      setTimeout(() => {
        if (textRef.current) textRef.current.scrollTop = textRef.current.scrollHeight;
      }, 50);
    } catch (err) {
      setLogError(err instanceof Error ? err.message : "加载日志失败");
    } finally {
      setLoadingContent(false);
    }
  }, []);

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
          <span className="text-xs text-gray-400">加载文件列表…</span>
        ) : files.length === 0 ? (
          <span className="text-xs text-gray-400">
            暂无日志文件（后端启动后会在 logs/ 目录下自动创建）
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
          <span>显示末尾</span>
          {[200, 500, 1000, 2000].map((n) => (
            <button
              key={n}
              onClick={() => setLines(n)}
              className={`rounded px-2 py-0.5 ${
                lines === n ? "bg-blue-600 text-white" : "border hover:bg-gray-100"
              }`}
            >
              {n}行
            </button>
          ))}
          {selected && (
            <button
              onClick={() => selected && loadContent(selected, lines)}
              className="rounded border px-2 py-0.5 hover:bg-gray-100"
            >
              刷新
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
          <span className="text-gray-500">加载中…</span>
        ) : content === null ? (
          <span className="text-gray-500">选择日志文件查看内容</span>
        ) : content.length === 0 ? (
          <span className="text-gray-500">日志文件为空</span>
        ) : (
          content
        )}
      </pre>
    </div>
  );
}

// ── 主组件 ────────────────────────────────────────────

export default function StatsTab() {
  const [innerTab, setInnerTab] = useState<"stats" | "logs">("stats");
  const [stats, setStats] = useState<Stats | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
        setError(err instanceof ApiError ? err.message : "加载失败");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (innerTab === "stats") load(days);
  }, [days, load, innerTab]);

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
      {/* 子 Tab：报表 / 日志 */}
      <div className="flex gap-1 border-b">
        {(["stats", "logs"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setInnerTab(t)}
            className={`px-4 py-2 text-sm ${
              innerTab === t
                ? "border-b-2 border-blue-600 font-medium text-blue-700"
                : "text-gray-500 hover:text-gray-800"
            }`}
          >
            {t === "stats" ? "使用报表" : "系统日志"}
          </button>
        ))}
      </div>

      {/* ── 报表 ── */}
      {innerTab === "stats" && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-600">时间范围：</span>
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
                近 {d} 天
              </button>
            ))}
            {loading && <span className="text-xs text-gray-400">加载中…</span>}
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
                <h3 className="mb-3 text-sm font-medium">活跃用户趋势</h3>
                <ActiveUsersChart data={stats?.active_users ?? []} />
              </div>

              {/* 各动作柱图 */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {actions.map((a) => (
                  <div key={a} className="rounded border bg-white p-4">
                    <h3 className="mb-3 text-sm font-medium">{ACTION_LABELS[a]}量</h3>
                    <MiniBarChart data={byAction(a)} color={ACTION_COLORS[a]} />
                  </div>
                ))}
              </div>

              {/* 用户明细表 */}
              <div className="rounded border bg-white">
                <div className="border-b px-4 py-3">
                  <h3 className="text-sm font-medium">用户使用明细</h3>
                </div>
                {(stats?.per_user ?? []).length === 0 ? (
                  <p className="px-4 py-6 text-center text-sm text-gray-400">暂无数据</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 text-xs text-gray-500">
                        <tr>
                          <th className="px-4 py-2 text-left">用户</th>
                          <th className="px-4 py-2 text-right">登录</th>
                          <th className="px-4 py-2 text-right">上传</th>
                          <th className="px-4 py-2 text-right">对话</th>
                          <th className="px-4 py-2 text-right">下载</th>
                          <th className="px-4 py-2 text-right font-semibold">合计</th>
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

      {/* ── 日志 ── */}
      {innerTab === "logs" && <LogViewer />}
    </div>
  );
}
