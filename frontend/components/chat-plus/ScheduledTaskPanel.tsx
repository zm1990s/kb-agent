"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import { api } from "@/lib/api";
import { useDialog } from "@/components/DialogProvider";

interface Skill {
  id: string;
  name: string;
}

interface ScheduledTask {
  id: string;
  name: string;
  enabled: boolean;
  schedule_type: "interval" | "daily" | "weekly" | "monthly";
  interval_minutes: number | null;
  daily_hour: number | null;
  daily_minute: number | null;
  week_day: number | null;
  month_day: number | null;
  system_prompt: string | null;
  initial_message: string;
  skill_ids: string[];
  workspace_id: string | null;
  locale: string;
  last_run_at: string | null;
  next_run_at: string | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

const UNITS = ["minutes", "hours", "days"] as const;
type Unit = (typeof UNITS)[number];

function unitToMinutes(value: number, unit: Unit): number {
  if (unit === "hours") return value * 60;
  if (unit === "days") return value * 60 * 24;
  return value;
}

function minutesToDisplay(minutes: number): { value: number; unit: Unit } {
  if (minutes % (60 * 24) === 0) return { value: minutes / (60 * 24), unit: "days" };
  if (minutes % 60 === 0) return { value: minutes / 60, unit: "hours" };
  return { value: minutes, unit: "minutes" };
}

// 时间选择器：HH:MM
function TimeSelect({
  hour,
  minute,
  onHourChange,
  onMinuteChange,
}: {
  hour: number;
  minute: number;
  onHourChange: (h: number) => void;
  onMinuteChange: (m: number) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <select
        value={hour}
        onChange={(e) => onHourChange(Number(e.target.value))}
        className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
      >
        {Array.from({ length: 24 }, (_, i) => (
          <option key={i} value={i}>{String(i).padStart(2, "0")}</option>
        ))}
      </select>
      <span className="text-sm text-gray-500">:</span>
      <select
        value={minute}
        onChange={(e) => onMinuteChange(Number(e.target.value))}
        className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
      >
        {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
          <option key={m} value={m}>{String(m).padStart(2, "0")}</option>
        ))}
      </select>
    </div>
  );
}

export default function ScheduledTaskPanel({ open, onClose }: Props) {
  const t = useTranslations("scheduledTask");
  const locale = useLocale();
  const { showConfirm } = useDialog();

  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ScheduledTask | null>(null);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);

  // form state
  const [fName, setFName] = useState("");
  const [fEnabled, setFEnabled] = useState(true);
  const [fScheduleType, setFScheduleType] = useState<ScheduledTask["schedule_type"]>("daily");
  const [fIntervalValue, setFIntervalValue] = useState(60);
  const [fIntervalUnit, setFIntervalUnit] = useState<Unit>("minutes");
  const [fHour, setFHour] = useState(9);
  const [fMinute, setFMinute] = useState(0);
  const [fWeekDay, setFWeekDay] = useState(0);   // 0=Mon…6=Sun
  const [fMonthDay, setFMonthDay] = useState(1);  // 1–31
  const [fMessage, setFMessage] = useState("");
  const [fSystemPrompt, setFSystemPrompt] = useState("");
  const [fSkillIds, setFSkillIds] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<ScheduledTask[]>("/scheduled-tasks");
      setTasks(data);
    } catch { /* 无权限时静默 */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!open) return;
    load();
    api.get<Skill[]>("/skills").then(setSkills).catch(() => setSkills([]));
  }, [open, load]);

  function openNew() {
    setEditing(null);
    setFName(""); setFEnabled(true); setFScheduleType("daily");
    setFIntervalValue(60); setFIntervalUnit("minutes");
    setFHour(9); setFMinute(0);
    setFWeekDay(0); setFMonthDay(1);
    setFMessage(""); setFSystemPrompt(""); setFSkillIds([]);
    setFormOpen(true);
  }

  function openEdit(task: ScheduledTask) {
    setEditing(task);
    setFName(task.name);
    setFEnabled(task.enabled);
    setFScheduleType(task.schedule_type);
    if (task.interval_minutes) {
      const { value, unit } = minutesToDisplay(task.interval_minutes);
      setFIntervalValue(value); setFIntervalUnit(unit);
    }
    setFHour(task.daily_hour ?? 9);
    setFMinute(task.daily_minute ?? 0);
    setFWeekDay(task.week_day ?? 0);
    setFMonthDay(task.month_day ?? 1);
    setFMessage(task.initial_message);
    setFSystemPrompt(task.system_prompt ?? "");
    setFSkillIds(task.skill_ids);
    setFormOpen(true);
  }

  async function save() {
    if (!fName.trim() || !fMessage.trim()) return;
    setSaving(true);
    const hasTime = fScheduleType !== "interval";
    const body = {
      name: fName.trim(),
      enabled: fEnabled,
      schedule_type: fScheduleType,
      interval_minutes: fScheduleType === "interval" ? unitToMinutes(fIntervalValue, fIntervalUnit) : null,
      daily_hour: hasTime ? fHour : null,
      daily_minute: hasTime ? fMinute : null,
      week_day: fScheduleType === "weekly" ? fWeekDay : null,
      month_day: fScheduleType === "monthly" ? fMonthDay : null,
      initial_message: fMessage.trim(),
      system_prompt: fSystemPrompt.trim() || null,
      skill_ids: fSkillIds,
      workspace_id: null,
      locale,
    };
    try {
      if (editing) {
        await api.patch(`/scheduled-tasks/${editing.id}`, body);
      } else {
        await api.post("/scheduled-tasks", body);
      }
      setFormOpen(false);
      await load();
    } catch { /* 静默 */ }
    finally { setSaving(false); }
  }

  async function deleteTask(task: ScheduledTask) {
    const ok = await showConfirm(t("deleteConfirm", { name: task.name }));
    if (!ok) return;
    try {
      await api.del(`/scheduled-tasks/${task.id}`);
      setTasks((prev) => prev.filter((t) => t.id !== task.id));
    } catch { /* 静默 */ }
  }

  async function runNow(task: ScheduledTask) {
    setRunningId(task.id);
    try {
      const updated = await api.post<ScheduledTask>(`/scheduled-tasks/${task.id}/run`, {});
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch { /* 静默 */ }
    finally { setRunningId(null); }
  }

  async function toggleEnabled(task: ScheduledTask) {
    try {
      const updated = await api.patch<ScheduledTask>(`/scheduled-tasks/${task.id}`, { enabled: !task.enabled });
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch { /* 静默 */ }
  }

  function formatSchedule(task: ScheduledTask): string {
    const h = String(task.daily_hour ?? 0).padStart(2, "0");
    const m = String(task.daily_minute ?? 0).padStart(2, "0");
    const timeStr = `${h}:${m}`;
    if (task.schedule_type === "daily") {
      return `${t("dailyAt")} ${timeStr} ${t("utcNote")}`;
    }
    if (task.schedule_type === "weekly") {
      const wdKey = String(task.week_day ?? 0) as "0";
      return `${t("weekDayLabel")} ${t(`weekDays.${wdKey}`)} ${timeStr} ${t("utcNote")}`;
    }
    if (task.schedule_type === "monthly") {
      return `${t("monthDayLabel")} ${task.month_day ?? 1} 号 ${timeStr} ${t("utcNote")}`;
    }
    // interval
    const min = task.interval_minutes ?? 5;
    const { value, unit } = minutesToDisplay(min);
    return `${t("intervalValue")} ${value} ${t(`units.${unit}`)}`;
  }

  function formatDate(iso: string | null): string {
    if (!iso) return t("never");
    return new Date(iso).toLocaleString();
  }

  if (!open) return null;

  const SCHEDULE_TYPES: ScheduledTask["schedule_type"][] = ["daily", "weekly", "monthly", "interval"];

  return (
    <div className="fixed inset-0 z-40 flex">
      {/* 遮罩 */}
      <div className="flex-1 bg-black/30" onClick={onClose} />
      {/* 面板 */}
      <div className="flex w-[440px] shrink-0 flex-col bg-white shadow-xl">
        {/* 顶栏 */}
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
          <h2 className="text-base font-semibold text-gray-900">{t("title")}</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={openNew}
              className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
            >
              {t("new")}
            </button>
            <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto">
          {/* 表单 */}
          {formOpen && (
            <div className="border-b border-gray-200 bg-gray-50 px-5 py-4">
              <h3 className="mb-3 text-sm font-semibold text-gray-800">{editing ? t("edit") : t("new")}</h3>
              <div className="space-y-3">
                {/* 名称 */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">{t("name")}</label>
                  <input
                    value={fName}
                    onChange={(e) => setFName(e.target.value)}
                    placeholder={t("namePlaceholder")}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
                  />
                </div>

                {/* 调度方式 */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">{t("scheduleType")}</label>
                  <div className="flex flex-wrap gap-3">
                    {SCHEDULE_TYPES.map((type) => (
                      <label key={type} className="flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer">
                        <input
                          type="radio"
                          value={type}
                          checked={fScheduleType === type}
                          onChange={() => setFScheduleType(type)}
                          className="accent-blue-600"
                        />
                        {t(type)}
                      </label>
                    ))}
                  </div>
                </div>

                {/* interval 设置 */}
                {fScheduleType === "interval" && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-600">{t("intervalValue")}</span>
                    <input
                      type="number"
                      min={1}
                      value={fIntervalValue}
                      onChange={(e) => setFIntervalValue(Number(e.target.value))}
                      className="w-20 rounded-lg border border-gray-300 px-2 py-1.5 text-sm outline-none focus:border-blue-500"
                    />
                    <select
                      value={fIntervalUnit}
                      onChange={(e) => setFIntervalUnit(e.target.value as Unit)}
                      className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    >
                      {UNITS.map((u) => (
                        <option key={u} value={u}>{t(`units.${u}`)}</option>
                      ))}
                    </select>
                  </div>
                )}

                {/* daily 设置 */}
                {fScheduleType === "daily" && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-600">{t("dailyAt")}</span>
                    <TimeSelect hour={fHour} minute={fMinute} onHourChange={setFHour} onMinuteChange={setFMinute} />
                    <span className="text-xs text-gray-400">{t("utcNote")}</span>
                  </div>
                )}

                {/* weekly 设置 */}
                {fScheduleType === "weekly" && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-gray-600">{t("weekDayLabel")}</span>
                    <select
                      value={fWeekDay}
                      onChange={(e) => setFWeekDay(Number(e.target.value))}
                      className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    >
                      {[0, 1, 2, 3, 4, 5, 6].map((d) => (
                        <option key={d} value={d}>{t(`weekDays.${d as 0}`)}</option>
                      ))}
                    </select>
                    <TimeSelect hour={fHour} minute={fMinute} onHourChange={setFHour} onMinuteChange={setFMinute} />
                    <span className="text-xs text-gray-400">{t("utcNote")}</span>
                  </div>
                )}

                {/* monthly 设置 */}
                {fScheduleType === "monthly" && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-gray-600">{t("monthDayLabel")}</span>
                    <select
                      value={fMonthDay}
                      onChange={(e) => setFMonthDay(Number(e.target.value))}
                      className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                    >
                      {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                    <span className="text-sm text-gray-600">{t("atTime")}</span>
                    <TimeSelect hour={fHour} minute={fMinute} onHourChange={setFHour} onMinuteChange={setFMinute} />
                    <span className="text-xs text-gray-400">{t("utcNote")}</span>
                  </div>
                )}

                {/* 初始消息 */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">{t("initialMessage")}</label>
                  <textarea
                    value={fMessage}
                    onChange={(e) => setFMessage(e.target.value)}
                    placeholder={t("initialMessagePlaceholder")}
                    rows={3}
                    className="w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
                  />
                </div>

                {/* 系统提示词 */}
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-600">{t("systemPrompt")}</label>
                  <textarea
                    value={fSystemPrompt}
                    onChange={(e) => setFSystemPrompt(e.target.value)}
                    placeholder={t("systemPromptPlaceholder")}
                    rows={2}
                    className="w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
                  />
                </div>

                {/* Skills */}
                {skills.length > 0 && (
                  <div>
                    <label className="mb-1 block text-xs font-medium text-gray-600">{t("skills")}</label>
                    <div className="flex flex-wrap gap-2">
                      {skills.map((s) => (
                        <label key={s.id} className="flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={fSkillIds.includes(s.id)}
                            onChange={(e) =>
                              setFSkillIds((prev) =>
                                e.target.checked ? [...prev, s.id] : prev.filter((id) => id !== s.id)
                              )
                            }
                            className="accent-blue-600"
                          />
                          {s.name}
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* 启用 */}
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={fEnabled}
                    onChange={(e) => setFEnabled(e.target.checked)}
                    className="accent-blue-600"
                  />
                  {t("enabled")}
                </label>

                {/* 文件说明 */}
                <p className="text-xs text-amber-600">{t("noFileNote")}</p>

                {/* 按钮 */}
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setFormOpen(false)}
                    className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
                  >
                    {t("cancel")}
                  </button>
                  <button
                    onClick={save}
                    disabled={saving || !fName.trim() || !fMessage.trim()}
                    className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
                  >
                    {saving ? "…" : t("save")}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 任务列表 */}
          {loading ? (
            <p className="px-5 py-8 text-center text-sm text-gray-400">{t("empty")}</p>
          ) : tasks.length === 0 && !formOpen ? (
            <p className="px-5 py-8 text-center text-sm text-gray-400">{t("empty")}</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {tasks.map((task) => (
                <li key={task.id} className="px-5 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-gray-900">{task.name}</p>
                      <p className="mt-0.5 text-xs text-gray-500">{formatSchedule(task)}</p>
                      <p className="mt-0.5 text-xs text-gray-400">
                        {t("lastRun")}: {formatDate(task.last_run_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {/* 启用 toggle */}
                      <button
                        onClick={() => toggleEnabled(task)}
                        title={t("enabled")}
                        className={`relative h-5 w-9 rounded-full transition-colors ${task.enabled ? "bg-blue-500" : "bg-gray-300"}`}
                      >
                        <span
                          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${task.enabled ? "translate-x-4" : "translate-x-0.5"}`}
                        />
                      </button>
                      {/* 立即运行 */}
                      <button
                        onClick={() => runNow(task)}
                        disabled={runningId === task.id}
                        title={t("runNow")}
                        className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-blue-600 disabled:opacity-40"
                      >
                        {runningId === task.id ? (
                          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                          </svg>
                        ) : (
                          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <polygon points="5 3 19 12 5 21 5 3" />
                          </svg>
                        )}
                      </button>
                      {/* 编辑 */}
                      <button
                        onClick={() => openEdit(task)}
                        title={t("edit")}
                        className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                      >
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      {/* 删除 */}
                      <button
                        onClick={() => deleteTask(task)}
                        title={t("delete")}
                        className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
                      >
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                          <polyline points="3 6 5 6 21 6" />
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 6l-1 14H6L5 6M10 11v6M14 11v6M9 6V4h6v2" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
