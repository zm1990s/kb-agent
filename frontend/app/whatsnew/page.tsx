"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import NavBar from "@/components/NavBar";
import Markdown from "@/components/Markdown";
import { api } from "@/lib/api";
import { getEmail, getToken, isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";

interface DocItem {
  doc_id: string;
  title: string;
  category: string;
  tags: string[];
  download_url: string;
}

interface WorkspaceReport {
  workspace_id: string;
  workspace_name: string;
  period_start: string;
  period_end: string;
  created_at: string;
  summary: string;
  documents: DocItem[];
}

interface Subscription {
  email: string;
  frequency: string;
  last_sent_at: string | null;
  created_at: string;
}

// FREQ_OPTIONS labels are now resolved via t() inside the component

function formatDate(iso: string) {
  return iso.slice(0, 10);
}

export default function WhatsNewPage() {
  const t = useTranslations("whatsnew");
  const ready = useAuthGuard("whatsnew");
  const admin = isAdmin();
  const myEmail = getEmail() ?? "";

  const FREQ_OPTIONS = [
    { value: "weekly", label: t("freq_weekly") },
    { value: "biweekly", label: t("freq_biweekly") },
    { value: "monthly", label: t("freq_monthly") },
  ];

  const [reports, setReports] = useState<WorkspaceReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState("");

  // 订阅状态
  const [sub, setSub] = useState<Subscription | null>(null);
  const [subLoading, setSubLoading] = useState(true);
  const [subFreq, setSubFreq] = useState("weekly");
  const [subSaving, setSubSaving] = useState(false);
  const [subMsg, setSubMsg] = useState("");

  async function load() {
    setLoading(true);
    try {
      const data = await api.get<WorkspaceReport[]>("/whatsnew");
      setReports(data);
    } catch {
      setReports([]);
    } finally {
      setLoading(false);
    }
  }

  async function loadSub() {
    setSubLoading(true);
    try {
      const data = await api.get<Subscription>("/whatsnew/subscription");
      setSub(data);
      setSubFreq(data.frequency);
    } catch {
      setSub(null);
    } finally {
      setSubLoading(false);
    }
  }

  useEffect(() => {
    if (ready) {
      load();
      loadSub();
    }
  }, [ready]);

  async function downloadDoc(doc: DocItem) {
    try {
      const token = getToken();
      const res = await fetch(`/api/documents/${doc.doc_id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.title;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silently ignore — no error state in this page for downloads
    }
  }

  async function handleTrigger() {
    setTriggering(true);
    setTriggerMsg("");
    try {
      await api.post("/whatsnew/trigger", {});
      setTriggerMsg(t("trigger_success"));
    } catch {
      setTriggerMsg(t("trigger_failed"));
    } finally {
      setTriggering(false);
    }
  }

  async function handleSubSave() {
    setSubSaving(true);
    setSubMsg("");
    try {
      const data = await api.put<Subscription>("/whatsnew/subscription", { frequency: subFreq });
      setSub(data);
      setSubMsg(t("sub_saved"));
    } catch {
      setSubMsg(t("sub_save_failed"));
    } finally {
      setSubSaving(false);
    }
  }

  async function handleSubDelete() {
    setSubSaving(true);
    setSubMsg("");
    try {
      await api.del("/whatsnew/subscription");
      setSub(null);
      setSubFreq("weekly");
      setSubMsg(t("sub_deleted"));
    } catch {
      setSubMsg(t("sub_delete_failed"));
    } finally {
      setSubSaving(false);
    }
  }

  if (!ready) return null;

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <NavBar />
      <main className="mx-auto w-full max-w-4xl flex-1 p-6">
        {/* 页头 */}
        <div className="mb-5 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-800">{t("title")}</h1>
          <div className="flex items-center gap-3">
            {admin && (
              <button
                onClick={handleTrigger}
                disabled={triggering}
                className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {triggering ? t("triggering") : t("trigger")}
              </button>
            )}
            <button
              onClick={load}
              className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
            >
              {t("refresh")}
            </button>
          </div>
        </div>

        {triggerMsg && (
          <div className="mb-4 rounded border border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-700">
            {triggerMsg}
          </div>
        )}

        {/* 摘要列表 */}
        {loading ? (
          <div className="py-16 text-center text-sm text-gray-400">{t("loading")}</div>
        ) : reports.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-400">
            {t("no_reports")}
          </div>
        ) : (
          <div className="space-y-6">
            {reports.map((r) => (
              <div
                key={r.workspace_id}
                className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm"
              >
                <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50 px-5 py-3">
                  <div className="font-medium text-gray-800">{r.workspace_name}</div>
                  <div className="text-xs text-gray-400">
                    {t("period", { start: formatDate(r.period_start), end: formatDate(r.period_end) })}
                    &nbsp;·&nbsp;{t("generated_at", { date: formatDate(r.created_at) })}
                  </div>
                </div>

                <div className="p-5">
                  {r.summary ? (
                    <div className="mb-4 rounded-lg border border-gray-100 bg-gray-50 px-4 py-3">
                      <Markdown content={r.summary} />
                    </div>
                  ) : null}

                  {r.documents.length > 0 && (
                    <div>
                      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
                        {t("new_docs", { count: r.documents.length })}
                      </p>
                      <ul className="space-y-2">
                        {r.documents.map((doc) => (
                          <li
                            key={doc.doc_id}
                            className="flex items-start gap-3 rounded-lg border border-gray-100 px-3 py-2.5 hover:bg-gray-50"
                          >
                            <svg
                              className="mt-0.5 h-4 w-4 shrink-0 text-blue-400"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                              strokeWidth={1.5}
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                              />
                            </svg>
                            <div className="min-w-0 flex-1">
                              <button
                                onClick={() => downloadDoc(doc)}
                                className="text-left text-sm font-medium text-blue-600 hover:underline"
                              >
                                {doc.title}
                              </button>
                              <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                                {doc.category && (
                                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                                    {doc.category}
                                  </span>
                                )}
                                {doc.tags.map((tag) => (
                                  <span
                                    key={tag}
                                    className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-500"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 邮件订阅区块 */}
        <div className="mt-10 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 bg-gray-50 px-5 py-3">
            <h2 className="font-medium text-gray-800">{t("subscription")}</h2>
          </div>
          <div className="p-5">
            {subLoading ? (
              <p className="text-sm text-gray-400">{t("loading")}</p>
            ) : (
              <div className="space-y-4">
                {/* 收件邮箱（只读） */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    {t("sub_email")}
                  </label>
                  <input
                    type="text"
                    value={myEmail}
                    readOnly
                    className="w-full rounded border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500 cursor-not-allowed"
                  />
                  <p className="mt-0.5 text-xs text-gray-400">{t("sub_email_hint")}</p>
                </div>

                {/* 频率选择 */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-500">
                    {t("sub_frequency")}
                  </label>
                  <select
                    value={subFreq}
                    onChange={(e) => setSubFreq(e.target.value)}
                    className="w-full rounded border border-gray-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
                  >
                    {FREQ_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 当前订阅状态 */}
                {sub && (
                  <p className="text-xs text-gray-400">
                    {t("sub_current", { freq: FREQ_OPTIONS.find((o) => o.value === sub.frequency)?.label ?? sub.frequency })}
                    {sub.last_sent_at
                      ? t("sub_last_sent", { date: formatDate(sub.last_sent_at) })
                      : t("sub_never_sent")}
                  </p>
                )}

                {/* 操作按钮 */}
                <div className="flex gap-2">
                  <button
                    onClick={handleSubSave}
                    disabled={subSaving}
                    className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {subSaving ? t("sub_save") : sub ? t("sub_update") : t("sub_subscribe")}
                  </button>
                  {sub && (
                    <button
                      onClick={handleSubDelete}
                      disabled={subSaving}
                      className="rounded border border-red-200 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      {t("sub_unsubscribe")}
                    </button>
                  )}
                </div>

                {subMsg && (
                  <p className={`text-sm ${subMsg.includes("失败") ? "text-red-600" : "text-green-600"}`}>
                    {subMsg}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
