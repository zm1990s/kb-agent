"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

interface DailyAction {
  day: string;
  action: string;
  count: number;
}
interface DailyActiveUser {
  day: string;
  users: number;
}
interface Stats {
  days: number;
  daily: DailyAction[];
  active_users: DailyActiveUser[];
  totals: Record<string, number>;
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

function MiniBarChart({
  data,
  label,
  color,
}: {
  data: { day: string; count: number }[];
  label: string;
  color: string;
}) {
  if (data.length === 0) return <p className="text-xs text-gray-400">暂无数据</p>;
  const max = Math.max(...data.map((d) => d.count), 1);
  const W = 360;
  const H = 80;
  const pad = 4;
  const barW = Math.max(2, Math.floor((W - pad * 2) / data.length) - 2);

  return (
    <div>
      <p className="mb-1 text-xs text-gray-500">{label}</p>
      <svg width={W} height={H} className="overflow-visible">
        {data.map((d, i) => {
          const bh = Math.max(2, Math.round((d.count / max) * (H - 20)));
          const x = pad + i * ((W - pad * 2) / data.length);
          const y = H - bh - 16;
          return (
            <g key={d.day}>
              <rect x={x} y={y} width={barW} height={bh} fill={color} rx={1} opacity={0.85}>
                <title>{d.day}: {d.count}</title>
              </rect>
            </g>
          );
        })}
        {/* x 轴首尾日期 */}
        {data.length > 0 && (
          <>
            <text x={pad} y={H} fontSize={9} fill="#9ca3af">{data[0].day.slice(5)}</text>
            <text x={W - pad - 30} y={H} fontSize={9} fill="#9ca3af">
              {data[data.length - 1].day.slice(5)}
            </text>
          </>
        )}
      </svg>
    </div>
  );
}

function ActiveUsersChart({ data }: { data: DailyActiveUser[] }) {
  if (data.length === 0) return <p className="text-xs text-gray-400">暂无数据</p>;
  const max = Math.max(...data.map((d) => d.users), 1);
  const W = 360;
  const H = 80;
  const pad = 4;

  const pts = data.map((d, i) => {
    const x = pad + (i / Math.max(data.length - 1, 1)) * (W - pad * 2);
    const y = H - 16 - (d.users / max) * (H - 20);
    return `${x},${y}`;
  });

  return (
    <div>
      <p className="mb-1 text-xs text-gray-500">活跃用户（每日去重）</p>
      <svg width={W} height={H} className="overflow-visible">
        <polyline
          points={pts.join(" ")}
          fill="none"
          stroke="#3b82f6"
          strokeWidth={1.5}
        />
        {data.map((d, i) => {
          const x = pad + (i / Math.max(data.length - 1, 1)) * (W - pad * 2);
          const y = H - 16 - (d.users / max) * (H - 20);
          return (
            <circle key={d.day} cx={x} cy={y} r={2.5} fill="#3b82f6">
              <title>{d.day}: {d.users} 人</title>
            </circle>
          );
        })}
        {data.length > 0 && (
          <>
            <text x={pad} y={H} fontSize={9} fill="#9ca3af">{data[0].day.slice(5)}</text>
            <text x={W - pad - 30} y={H} fontSize={9} fill="#9ca3af">
              {data[data.length - 1].day.slice(5)}
            </text>
          </>
        )}
      </svg>
    </div>
  );
}

export default function StatsTab() {
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
      setError(err instanceof ApiError ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(days);
  }, [days, load]);

  // 将 daily 数据按 action 分组
  function byAction(action: string) {
    const map: Record<string, number> = {};
    (stats?.daily ?? [])
      .filter((d) => d.action === action)
      .forEach((d) => {
        map[d.day] = (map[d.day] ?? 0) + d.count;
      });
    // 生成完整日期序列（以 active_users 的日期为准，补 0）
    const days_list = stats?.active_users.map((d) => d.day) ?? Object.keys(map).sort();
    return days_list.map((day) => ({ day, count: map[day] ?? 0 }));
  }

  const actions = Object.keys(ACTION_LABELS);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-600">时间范围：</span>
        {[7, 14, 30, 90].map((d) => (
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
      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* 汇总卡片 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {actions.map((a) => (
          <div key={a} className="rounded border bg-white p-4 text-center">
            <p className="text-2xl font-bold" style={{ color: ACTION_COLORS[a] }}>
              {stats?.totals[a] ?? 0}
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
            <MiniBarChart
              data={byAction(a)}
              label=""
              color={ACTION_COLORS[a]}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
