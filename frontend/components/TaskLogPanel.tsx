"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";
import type { ProcessingTask } from "@/lib/types";

// 文档处理任务的日志/错误详情面板（模态）。
export default function TaskLogPanel({
  documentId,
  title,
  onClose,
}: {
  documentId: string;
  title: string;
  onClose: () => void;
}) {
  const t = useTranslations("taskLog");
  const [tasks, setTasks] = useState<ProcessingTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ProcessingTask[]>(`/documents/${documentId}/tasks`)
      .then(setTasks)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : t("load_failed"))
      );
  }, [documentId]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="truncate text-sm font-semibold">{t("title", { name: title })}</h2>
          <button
            onClick={onClose}
            className="rounded px-2 text-gray-400 hover:bg-gray-100"
          >
            ✕
          </button>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {!tasks && !error && <p className="text-sm text-gray-400">{t("loading")}</p>}
        {tasks && tasks.length === 0 && (
          <p className="text-sm text-gray-400">{t("no_tasks")}</p>
        )}

        <div className="space-y-4">
          {tasks?.map((task, i) => (
            <div key={task.id} className="rounded border">
              <div className="flex items-center justify-between border-b bg-gray-50 px-3 py-2 text-xs">
                <span>
                  {t("attempt", { n: i + 1, attempts: task.attempts, max: task.max_attempts })}
                </span>
                <span
                  className={
                    task.status === "succeeded"
                      ? "text-green-700"
                      : task.status === "failed"
                        ? "text-red-600"
                        : "text-amber-600"
                  }
                >
                  {task.status === "queued" ? t("status_queued")
                    : task.status === "running" ? t("status_running")
                    : task.status === "succeeded" ? t("status_succeeded")
                    : task.status === "failed" ? t("status_failed")
                    : task.status}
                </span>
              </div>
              {task.error && (
                <p className="border-b bg-red-50 px-3 py-2 text-xs text-red-700">
                  {t("error_prefix", { msg: task.error })}
                </p>
              )}
              <ul className="divide-y text-xs">
                {task.logs.map((log, j) => (
                  <li key={j} className="flex gap-2 px-3 py-1.5">
                    <span className="shrink-0 text-gray-400">
                      {new Date(log.at).toLocaleTimeString()}
                    </span>
                    <span className="shrink-0 font-mono text-gray-500">
                      [{log.stage}]
                    </span>
                    <span className="text-gray-700">{log.message}</span>
                  </li>
                ))}
                {task.logs.length === 0 && (
                  <li className="px-3 py-1.5 text-gray-400">{t("no_logs")}</li>
                )}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
