"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

interface PromptItem {
  key: string;
  label: string;
  description: string;
  value: string;
  required_placeholders: string[];
}

interface HistoryEntry {
  id: number;
  prompt_key: string;
  version: number;
  value: string;
  created_at: string;
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

// 逐行 diff：返回每行的状态 add | remove | equal
function diffLines(a: string, b: string): { type: "equal" | "remove" | "add"; text: string }[] {
  const la = a.split("\n");
  const lb = b.split("\n");
  // 简单 LCS-based line diff
  const m = la.length, n = lb.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--)
    for (let j = n - 1; j >= 0; j--)
      dp[i][j] = la[i] === lb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);

  const result: { type: "equal" | "remove" | "add"; text: string }[] = [];
  let i = 0, j = 0;
  while (i < m || j < n) {
    if (i < m && j < n && la[i] === lb[j]) {
      result.push({ type: "equal", text: la[i] });
      i++; j++;
    } else if (j < n && (i >= m || dp[i + 1]?.[j] <= dp[i]?.[j + 1])) {
      result.push({ type: "add", text: lb[j] });
      j++;
    } else {
      result.push({ type: "remove", text: la[i] });
      i++;
    }
  }
  return result;
}

// 单个提示词卡片
function PromptCard({ prompt, onSaved }: { prompt: PromptItem; onSaved: (p: PromptItem) => void }) {
  const [draft, setDraft] = useState(prompt.value);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 历史面板
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [histLoading, setHistLoading] = useState(false);

  // Diff 面板
  const [diffLeft, setDiffLeft] = useState<number | null>(null);
  const [diffRight, setDiffRight] = useState<number | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  const loadHistory = useCallback(async () => {
    setHistLoading(true);
    try {
      const data = await api.get<HistoryEntry[]>(`/settings/prompts/${prompt.key}/history`);
      setHistory(data);
    } catch {
      // ignore
    } finally {
      setHistLoading(false);
    }
  }, [prompt.key]);

  useEffect(() => {
    if (showHistory) loadHistory();
  }, [showHistory, loadHistory]);

  // 同步外部更新（回退后父组件刷新 prompt.value）
  useEffect(() => { setDraft(prompt.value); }, [prompt.value]);

  async function save() {
    setSaving(true); setMsg(null); setError(null);
    try {
      const updated = await api.put<PromptItem>(`/settings/prompts/${prompt.key}`, { value: draft });
      onSaved(updated);
      setMsg("已保存");
      if (showHistory) loadHistory();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function rollback(version: number) {
    setSaving(true); setMsg(null); setError(null);
    try {
      const updated = await api.post<PromptItem>(`/settings/prompts/${prompt.key}/rollback`, { version });
      onSaved(updated);
      setDraft(updated.value);
      setMsg(`已回退到 v${version}`);
      loadHistory();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "回退失败");
    } finally {
      setSaving(false);
    }
  }

  async function resetDefault() {
    setSaving(true); setMsg(null); setError(null);
    try {
      const updated = await api.put<PromptItem>(`/settings/prompts/${prompt.key}/reset`, {});
      onSaved(updated);
      setDraft(updated.value);
      setMsg("已恢复默认");
      if (showHistory) loadHistory();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "重置失败");
    } finally {
      setSaving(false);
    }
  }

  // diff 计算
  const leftEntry = history.find((h) => h.version === diffLeft);
  const rightEntry = history.find((h) => h.version === diffRight);
  const diffResult = leftEntry && rightEntry ? diffLines(leftEntry.value, rightEntry.value) : null;

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      {/* 标题行 */}
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-800">{prompt.label}</h2>
        <button
          onClick={() => { setShowHistory((v) => !v); setShowDiff(false); }}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 transition-colors"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          历史版本
        </button>
      </div>
      <p className="mb-2 text-xs text-gray-400">{prompt.description}</p>
      {prompt.required_placeholders.length > 0 && (
        <p className="mb-3 text-xs text-blue-600">
          必须包含：{prompt.required_placeholders.map((ph) => (
            <code key={ph} className="mx-0.5 rounded bg-blue-50 px-1 font-mono">{ph}</code>
          ))}
        </p>
      )}

      {/* 编辑区 */}
      <textarea
        value={draft}
        onChange={(e) => { setDraft(e.target.value); setMsg(null); }}
        rows={Math.max(6, draft.split("\n").length + 1)}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-xs leading-relaxed focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
      />

      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      {msg && <p className="mt-1 text-xs text-green-600">{msg}</p>}

      <div className="mt-2 flex flex-wrap gap-2">
        <button
          onClick={save}
          disabled={saving || draft === prompt.value}
          className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving ? "保存中…" : "保存"}
        </button>
        <button
          onClick={resetDefault}
          disabled={saving}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition-colors"
        >
          恢复默认
        </button>
        <button
          onClick={() => setDraft(prompt.value)}
          disabled={draft === prompt.value}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50 disabled:opacity-40 transition-colors"
        >
          撤销更改
        </button>
      </div>

      {/* 历史版本面板 */}
      {showHistory && (
        <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">历史版本</span>
            {!showDiff && history.length >= 2 && (
              <button
                onClick={() => {
                  setDiffLeft(history[1]?.version ?? null);
                  setDiffRight(history[0]?.version ?? null);
                  setShowDiff(true);
                }}
                className="rounded px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-50 transition-colors"
              >
                对比视图
              </button>
            )}
            {showDiff && (
              <button
                onClick={() => setShowDiff(false)}
                className="rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-100"
              >
                关闭对比
              </button>
            )}
          </div>

          {histLoading && <p className="text-xs text-gray-400">加载中…</p>}
          {!histLoading && history.length === 0 && (
            <p className="text-xs text-gray-400">尚无历史版本（保存后产生记录）</p>
          )}

          {/* 对比面板 */}
          {showDiff && (
            <div className="mb-3">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-xs text-gray-500">对比：</span>
                <select
                  value={diffLeft ?? ""}
                  onChange={(e) => setDiffLeft(Number(e.target.value))}
                  className="rounded border px-2 py-0.5 text-xs"
                >
                  {history.map((h) => (
                    <option key={h.version} value={h.version}>
                      v{h.version} · {fmtDate(h.created_at)}
                    </option>
                  ))}
                </select>
                <span className="text-xs text-gray-400">→</span>
                <select
                  value={diffRight ?? ""}
                  onChange={(e) => setDiffRight(Number(e.target.value))}
                  className="rounded border px-2 py-0.5 text-xs"
                >
                  {history.map((h) => (
                    <option key={h.version} value={h.version}>
                      v{h.version} · {fmtDate(h.created_at)}
                    </option>
                  ))}
                </select>
              </div>
              {diffResult && (
                <div className="overflow-auto rounded border border-gray-200 bg-white">
                  <table className="w-full border-collapse font-mono text-xs">
                    <tbody>
                      {diffResult.map((line, i) => (
                        <tr
                          key={i}
                          className={
                            line.type === "add"
                              ? "bg-green-50"
                              : line.type === "remove"
                              ? "bg-red-50"
                              : ""
                          }
                        >
                          <td className="w-5 select-none border-r border-gray-200 px-1.5 text-center text-gray-400">
                            {line.type === "add" ? "+" : line.type === "remove" ? "−" : " "}
                          </td>
                          <td
                            className={`whitespace-pre-wrap break-all px-2 py-0.5 ${
                              line.type === "add"
                                ? "text-green-800"
                                : line.type === "remove"
                                ? "text-red-700"
                                : "text-gray-700"
                            }`}
                          >
                            {line.text || " "}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* 版本列表 */}
          {!histLoading && history.length > 0 && (
            <ul className="space-y-1">
              {history.map((h) => (
                <li
                  key={h.id}
                  className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-3 py-2"
                >
                  <div className="min-w-0">
                    <span className="mr-2 inline-block rounded bg-blue-100 px-1.5 py-0.5 text-xs font-semibold text-blue-700">
                      v{h.version}
                    </span>
                    <span className="text-xs text-gray-500">{fmtDate(h.created_at)}</span>
                  </div>
                  <div className="ml-3 flex shrink-0 gap-2">
                    <button
                      onClick={() => {
                        setDiffLeft(h.version);
                        setDiffRight(history[0]?.version ?? h.version);
                        setShowDiff(true);
                      }}
                      className="rounded px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-50 transition-colors"
                    >
                      与最新对比
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(`确认回退到 v${h.version}？当前内容将被保存为新版本。`))
                          rollback(h.version);
                      }}
                      disabled={saving}
                      className="rounded px-2 py-0.5 text-xs text-orange-600 hover:bg-orange-50 disabled:opacity-50 transition-colors"
                    >
                      回退
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

export default function PromptsTab() {
  const [prompts, setPrompts] = useState<PromptItem[]>([]);

  useEffect(() => {
    api.get<PromptItem[]>("/settings/prompts").then(setPrompts).catch(() => {});
  }, []);

  function handleSaved(updated: PromptItem) {
    setPrompts((ps) => ps.map((p) => (p.key === updated.key ? updated : p)));
  }

  if (prompts.length === 0) return <p className="text-sm text-gray-400">加载中…</p>;

  return (
    <div className="space-y-5">
      {prompts.map((p) => (
        <PromptCard key={p.key} prompt={p} onSaved={handleSaved} />
      ))}
    </div>
  );
}
