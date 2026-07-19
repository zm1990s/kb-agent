"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";

interface EngineOption {
  id: string;
  label: string;
  available: boolean;
}
interface EngineConfig {
  current: string;
  options: EngineOption[];
}
interface TaskModel {
  key: string;
  label: string;
  model: string | null;
}
interface TaskModelsConfig {
  default_model: string;
  tasks: TaskModel[];
}
interface ChatEngineConfig {
  chat_engine_backend: string;
  openai_base_url: string;
  openai_api_key: string;
  openai_model: string;
}
type TaskHeadersConfig = Record<"classify" | "title" | "chat" | "whatsnew", Record<string, string>>;

const TASK_KEYS = ["classify", "title", "chat", "whatsnew"] as const;

type AISec = "agent" | "chat_engine" | "task_headers";

export default function AIEngineSettings() {
  const t = useTranslations("settings");
  const ta = useTranslations("admin");
  const [activeSec, setActiveSec] = useState<AISec>("agent");

  const [error, setError] = useState<string | null>(null);

  // 默认 Agent 引擎
  const [engine, setEngine] = useState<EngineConfig | null>(null);
  const [engineMsg, setEngineMsg] = useState<string | null>(null);

  // 任务级模型
  const [taskModels, setTaskModels] = useState<TaskModelsConfig | null>(null);
  const [taskModelInputs, setTaskModelInputs] = useState<Record<string, string>>({});
  const [taskModelMsg, setTaskModelMsg] = useState<string | null>(null);

  // 对话引擎
  const [chatEngine, setChatEngine] = useState<ChatEngineConfig>({
    chat_engine_backend: "claude_cli",
    openai_base_url: "",
    openai_api_key: "",
    openai_model: "",
  });
  const [chatEngineInput, setChatEngineInput] = useState<ChatEngineConfig>({
    chat_engine_backend: "claude_cli",
    openai_base_url: "",
    openai_api_key: "",
    openai_model: "",
  });
  const [chatEngineMsg, setChatEngineMsg] = useState<string | null>(null);

  // 任务请求 Headers
  const [taskHeaders, setTaskHeaders] = useState<TaskHeadersConfig>({
    classify: { "x-portkey-metadata": '{"x-task": "classify"}' },
    title:    { "x-portkey-metadata": '{"x-task": "title"}' },
    chat:     { "x-portkey-metadata": '{"x-task": "chat"}' },
    whatsnew: { "x-portkey-metadata": '{"x-task": "whatsnew"}' },
  });
  const [taskHeadersMsg, setTaskHeadersMsg] = useState<string | null>(null);

  const loadEngine = useCallback(async () => {
    try {
      setEngine(await api.get<EngineConfig>("/settings/engine"));
    } catch { /* no-op */ }
  }, []);

  const loadTaskModels = useCallback(async () => {
    try {
      const d = await api.get<TaskModelsConfig>("/settings/models");
      setTaskModels(d);
      const inputs: Record<string, string> = {};
      for (const task of d.tasks) inputs[task.key] = task.model ?? "";
      setTaskModelInputs(inputs);
    } catch { /* no-op */ }
  }, []);

  const loadChatEngine = useCallback(async () => {
    try {
      const d = await api.get<ChatEngineConfig>("/settings/chat-engine");
      setChatEngine(d);
      setChatEngineInput({ ...d, openai_api_key: "" });
    } catch { /* no-op */ }
  }, []);

  const loadTaskHeaders = useCallback(async () => {
    try {
      const d = await api.get<TaskHeadersConfig>("/settings/task-headers");
      setTaskHeaders(d);
    } catch { /* no-op */ }
  }, []);

  useEffect(() => {
    loadEngine();
    loadTaskModels();
    loadChatEngine();
    loadTaskHeaders();
  }, [loadEngine, loadTaskModels, loadChatEngine, loadTaskHeaders]);

  async function selectEngine(backend: string) {
    setError(null);
    setEngineMsg(null);
    try {
      const updated = await api.put<EngineConfig>("/settings/engine", { backend });
      setEngine(updated);
      setEngineMsg(t("engine_updated"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("update_failed"));
    }
  }

  async function saveTaskModel(key: string) {
    setError(null);
    setTaskModelMsg(null);
    try {
      const model = taskModelInputs[key]?.trim() || null;
      await api.put(`/settings/models/${key}`, { model });
      await loadTaskModels();
      setTaskModelMsg(t("task_model_saved"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
    }
  }

  async function saveChatEngine(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setChatEngineMsg(null);
    try {
      const updated = await api.put<ChatEngineConfig>("/settings/chat-engine", chatEngineInput);
      if (updated) {
        setChatEngine(updated);
        setChatEngineInput({ ...updated, openai_api_key: "" });
      }
      setChatEngineMsg(t("chat_engine_saved"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
    }
  }

  async function saveTaskHeadersForTask(task: typeof TASK_KEYS[number]) {
    setTaskHeadersMsg(null);
    try {
      const updated = await api.put<TaskHeadersConfig>(`/settings/task-headers/${task}`, {
        headers: taskHeaders[task],
      });
      setTaskHeaders(updated);
      setTaskHeadersMsg(t("task_headers_saved"));
      setTimeout(() => setTaskHeadersMsg(null), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
    }
  }

  function updateTaskHeaderKey(task: typeof TASK_KEYS[number], oldKey: string, newKey: string) {
    setTaskHeaders((prev) => {
      const entries = Object.entries(prev[task]);
      const idx = entries.findIndex(([k]) => k === oldKey);
      if (idx === -1) return prev;
      entries[idx] = [newKey, entries[idx][1]];
      return { ...prev, [task]: Object.fromEntries(entries) };
    });
  }

  function updateTaskHeaderValue(task: typeof TASK_KEYS[number], key: string, value: string) {
    setTaskHeaders((prev) => ({ ...prev, [task]: { ...prev[task], [key]: value } }));
  }

  function addTaskHeaderRow(task: typeof TASK_KEYS[number]) {
    setTaskHeaders((prev) => ({ ...prev, [task]: { ...prev[task], "": "" } }));
  }

  function removeTaskHeaderRow(task: typeof TASK_KEYS[number], key: string) {
    setTaskHeaders((prev) => {
      const next = { ...prev[task] };
      delete next[key];
      return { ...prev, [task]: next };
    });
  }

  const AI_SECTIONS: [AISec, string][] = [
    ["agent", ta("ai_section_agent")],
    ["chat_engine", ta("ai_section_chat_engine")],
    ["task_headers", ta("ai_section_task_headers")],
  ];

  return (
    <div className="flex gap-6">
      {/* 左侧菜单 */}
      <aside className="w-40 shrink-0 flex flex-col gap-0.5">
        {AI_SECTIONS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setActiveSec(key)}
            className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
              activeSec === key
                ? "bg-blue-50 text-blue-700 font-medium"
                : "text-gray-700 hover:bg-gray-100"
            }`}
          >
            {label}
          </button>
        ))}
      </aside>

      {/* 右侧内容 */}
      <div className="flex-1 min-w-0 space-y-6">
      {/* 默认 Agent 引擎 */}
      {activeSec === "agent" && <section className="rounded border bg-white p-4">
        <h2 className="mb-1 text-sm font-medium">{t("engine_title")}</h2>
        <p className="mb-3 text-xs text-gray-400">{t("engine_desc")}</p>
        <div className="space-y-2">
          {engine?.options.map((o) => (
            <label
              key={o.id}
              className={`flex items-center gap-2 rounded border px-3 py-2 text-sm ${
                o.available
                  ? "cursor-pointer hover:bg-gray-50"
                  : "cursor-not-allowed bg-gray-50 text-gray-400"
              } ${engine.current === o.id ? "border-blue-500 bg-blue-50" : ""}`}
            >
              <input
                type="radio"
                name="engine"
                disabled={!o.available}
                checked={engine.current === o.id}
                onChange={() => selectEngine(o.id)}
              />
              {o.label}
              {engine.current === o.id && (
                <span className="ml-auto text-xs text-blue-600">{t("engine_current")}</span>
              )}
            </label>
          ))}
          {!engine && <p className="text-sm text-gray-400">{t("engine_loading")}</p>}
        </div>
        {engineMsg && <p className="mt-2 text-xs text-green-600">{engineMsg}</p>}

        {/* 任务级模型配置（子菜单） */}
        <div className="mt-4 rounded border border-gray-100 bg-gray-50 p-3">
          <h3 className="mb-1 text-xs font-medium text-gray-700">{t("task_model_title")}</h3>
          <p className="mb-3 text-xs text-gray-400">
            {t("task_model_desc", { default: taskModels ? taskModels.default_model : t("task_model_loading") })}
          </p>
          {taskModels ? (
            <div className="space-y-3">
              {taskModels.tasks.map((task) => (
                <div key={task.key} className="flex items-center gap-2">
                  <label className="w-36 flex-shrink-0 text-xs text-gray-600">
                    {{ classify: t("task_classify"), chat: t("task_chat"), whatsnew: t("task_whatsnew"), title: t("task_title") }[task.key.split("::")[1]] ?? task.key}
                  </label>
                  <input
                    value={taskModelInputs[task.key] ?? ""}
                    onChange={(e) =>
                      setTaskModelInputs((prev) => ({ ...prev, [task.key]: e.target.value }))
                    }
                    placeholder={taskModels.default_model}
                    className="flex-1 rounded border bg-white px-3 py-1.5 text-sm font-mono focus:border-blue-400 focus:outline-none"
                  />
                  <button
                    onClick={() => saveTaskModel(task.key)}
                    className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
                  >
                    {t("whatsnew_save")}
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">{t("task_model_loading")}</p>
          )}
          {taskModelMsg && <p className="mt-2 text-xs text-green-600">{taskModelMsg}</p>}
        </div>
      </section>}

      {/* 对话引擎 */}
      {activeSec === "chat_engine" && <section className="rounded border bg-white p-4">
        <h2 className="mb-1 text-sm font-medium">{t("chat_engine_title")}</h2>
        <p className="mb-3 text-xs text-gray-400">{t("chat_engine_desc")}</p>
        <form onSubmit={saveChatEngine} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-gray-500">{t("chat_engine_backend_label")}</label>
            <select
              value={chatEngineInput.chat_engine_backend}
              onChange={(e) => setChatEngineInput((prev) => ({ ...prev, chat_engine_backend: e.target.value }))}
              className="rounded border px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
            >
              <option value="claude_cli">{t("chat_engine_claude_cli")}</option>
              <option value="openai_compat">{t("chat_engine_openai_compat")}</option>
            </select>
          </div>
          {chatEngineInput.chat_engine_backend === "openai_compat" && (
            <div className="space-y-2 rounded border border-gray-100 bg-gray-50 p-3">
              <div>
                <label className="mb-1 block text-xs text-gray-500">{t("openai_base_url_label")}</label>
                <input
                  value={chatEngineInput.openai_base_url}
                  onChange={(e) => setChatEngineInput((prev) => ({ ...prev, openai_base_url: e.target.value }))}
                  placeholder="http://localhost:11434/v1"
                  className="w-full rounded border px-3 py-1.5 text-sm font-mono focus:border-blue-400 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500">
                  {t("openai_api_key_label")}
                  {chatEngine.openai_api_key === "***" && (
                    <span className="ml-2 text-gray-400">{t("openai_api_key_set")}</span>
                  )}
                </label>
                <input
                  type="password"
                  value={chatEngineInput.openai_api_key}
                  onChange={(e) => setChatEngineInput((prev) => ({ ...prev, openai_api_key: e.target.value }))}
                  placeholder={chatEngine.openai_api_key === "***" ? t("openai_api_key_set") : "none"}
                  className="w-full rounded border px-3 py-1.5 text-sm font-mono focus:border-blue-400 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500">{t("openai_model_label")}</label>
                <input
                  value={chatEngineInput.openai_model}
                  onChange={(e) => setChatEngineInput((prev) => ({ ...prev, openai_model: e.target.value }))}
                  placeholder="qwen2.5:72b"
                  className="w-full rounded border px-3 py-1.5 text-sm font-mono focus:border-blue-400 focus:outline-none"
                />
              </div>
            </div>
          )}
          <button
            type="submit"
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            {t("whatsnew_save")}
          </button>
        </form>
        {chatEngineMsg && <p className="mt-2 text-xs text-green-600">{chatEngineMsg}</p>}
      </section>}

      {/* 任务请求 Headers */}
      {activeSec === "task_headers" && <section className="rounded border bg-white p-4">
        <h2 className="mb-1 text-sm font-medium">{t("task_headers_title")}</h2>
        <p className="mb-4 text-xs text-gray-400">{t("task_headers_desc")}</p>
        <div className="space-y-5">
          {TASK_KEYS.map((task) => (
            <div key={task}>
              <p className="mb-2 text-xs font-medium text-gray-600">
                {t(`task_${task}` as Parameters<typeof t>[0])}
              </p>
              <div className="space-y-1.5">
                {Object.entries(taskHeaders[task]).map(([k, v], idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <input
                      className="w-5/12 rounded border px-2 py-1 text-xs font-mono"
                      value={k}
                      placeholder={t("task_headers_key_placeholder")}
                      onChange={(e) => updateTaskHeaderKey(task, k, e.target.value)}
                    />
                    <input
                      className="flex-1 rounded border px-2 py-1 text-xs font-mono"
                      value={v}
                      placeholder={t("task_headers_value_placeholder")}
                      onChange={(e) => updateTaskHeaderValue(task, k, e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={() => removeTaskHeaderRow(task, k)}
                      className="shrink-0 rounded px-2 py-1 text-xs text-gray-400 hover:bg-red-50 hover:text-red-500"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => addTaskHeaderRow(task)}
                  className="rounded border px-2 py-1 text-xs text-gray-500 hover:bg-gray-50"
                >
                  + {t("task_headers_add")}
                </button>
                <button
                  type="button"
                  onClick={() => saveTaskHeadersForTask(task)}
                  className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
                >
                  {t("task_headers_save")}
                </button>
              </div>
            </div>
          ))}
        </div>
        {taskHeadersMsg && <p className="mt-3 text-xs text-green-600">{taskHeadersMsg}</p>}
      </section>}

      {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </div>
  );
}
