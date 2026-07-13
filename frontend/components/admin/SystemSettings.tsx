"use client";

import { useCallback, useEffect, useState } from "react";
import PromptsTab from "@/components/admin/PromptsTab";
import { api, ApiError } from "@/lib/api";
import type { AllowedDomain } from "@/lib/types";

interface EngineOption {
  id: string;
  label: string;
  available: boolean;
}
interface EngineConfig {
  current: string;
  options: EngineOption[];
}
interface Branding {
  name: string;
  logo_url: string;
}

type Tab = "general" | "prompts";

export default function SystemSettings() {
  const [tab, setTab] = useState<Tab>("general");
  const [domains, setDomains] = useState<AllowedDomain[]>([]);
  const [domainName, setDomainName] = useState("");
  const [engine, setEngine] = useState<EngineConfig | null>(null);
  const [branding, setBranding] = useState<Branding>({ name: "", logo_url: "" });
  const [brandingName, setBrandingName] = useState("");
  const [brandingLogo, setBrandingLogo] = useState("");
  const [wnHour, setWnHour] = useState<number>(2);
  const [wnHourInput, setWnHourInput] = useState<number>(2);
  const [wnFreq, setWnFreq] = useState<string>("weekly");
  const [wnFreqInput, setWnFreqInput] = useState<string>("weekly");
  const [wnFreqOptions, setWnFreqOptions] = useState<string[]>([]);
  const [wnTriggering, setWnTriggering] = useState(false);
  const [wnMsg, setWnMsg] = useState<string | null>(null);
  const [sqText, setSqText] = useState("");
  const [sqMsg, setSqMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [brandingMsg, setBrandingMsg] = useState<string | null>(null);
  const [engineMsg, setEngineMsg] = useState<string | null>(null);

  const loadDomains = useCallback(async () => {
    try {
      setDomains(await api.get<AllowedDomain[]>("/auth/allowed-domains"));
    } catch {
      setDomains([]);
    }
  }, []);

  const loadEngine = useCallback(async () => {
    try {
      setEngine(await api.get<EngineConfig>("/settings/engine"));
    } catch {
      setEngine(null);
    }
  }, []);

  const loadBranding = useCallback(async () => {
    try {
      const b = await api.get<Branding>("/settings/branding");
      setBranding(b);
      setBrandingName(b.name);
      setBrandingLogo(b.logo_url);
    } catch {
      // 非管理员读不到也没关系
    }
  }, []);

  const loadWnSchedule = useCallback(async () => {
    try {
      const d = await api.get<{ hour: number; frequency: string; frequency_options: string[] }>("/settings/whatsnew-schedule");
      setWnHour(d.hour);
      setWnHourInput(d.hour);
      setWnFreq(d.frequency);
      setWnFreqInput(d.frequency);
      setWnFreqOptions(d.frequency_options);
    } catch { /* 非 admin 正常 */ }
  }, []);

  const loadSuggestedQuestions = useCallback(async () => {
    try {
      const d = await api.get<{ questions: string[] }>("/settings/suggested-questions");
      setSqText(d.questions.join("\n"));
    } catch { /* 非 admin 正常 */ }
  }, []);

  useEffect(() => {
    loadDomains();
    loadEngine();
    loadBranding();
    loadWnSchedule();
    loadSuggestedQuestions();
  }, [loadDomains, loadEngine, loadBranding, loadWnSchedule, loadSuggestedQuestions]);

  async function addDomain(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/auth/allowed-domains", { domain: domainName });
      setDomainName("");
      await loadDomains();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "添加失败");
    }
  }

  async function deleteDomain(id: string) {
    setError(null);
    try {
      await api.del(`/auth/allowed-domains/${id}`);
      await loadDomains();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  async function saveBranding(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBrandingMsg(null);
    try {
      const updated = await api.put<Branding>("/settings/branding", {
        name: brandingName,
        logo_url: brandingLogo,
      });
      setBranding(updated);
      setBrandingMsg("品牌配置已保存，刷新页面生效");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    }
  }

  const FREQ_LABELS: Record<string, string> = {
    daily: "每天",
    weekly: "每周",
    biweekly: "每两周",
    monthly: "每月",
  };

  async function saveWnSchedule(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setWnMsg(null);
    try {
      const d = await api.put<{ hour: number; frequency: string }>(
        "/settings/whatsnew-schedule",
        { hour: wnHourInput, frequency: wnFreqInput },
      );
      setWnHour(d.hour);
      setWnFreq(d.frequency);
      setWnMsg(`新动态将${FREQ_LABELS[d.frequency] ?? d.frequency}在 ${d.hour}:00 UTC 生成`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    }
  }

  async function triggerWnNow() {
    setWnTriggering(true);
    setWnMsg(null);
    setError(null);
    try {
      await api.post("/whatsnew/trigger", {});
      setWnMsg("摘要生成任务已提交，请稍后在新动态页面查看结果。");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "触发失败");
    } finally {
      setWnTriggering(false);
    }
  }

  async function selectEngine(backend: string) {
    setError(null);
    setEngineMsg(null);
    try {
      const updated = await api.put<EngineConfig>("/settings/engine", { backend });
      setEngine(updated);
      setEngineMsg("引擎已更新");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  async function saveSuggestedQuestions(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSqMsg(null);
    try {
      const questions = sqText.split("\n").map((q) => q.trim()).filter(Boolean);
      const updated = await api.put<{ questions: string[] }>("/settings/suggested-questions", { questions });
      setSqText(updated.questions.join("\n"));
      setSqMsg(`已保存 ${updated.questions.length} 条引导问题`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败");
    }
  }

  return (
    <div>
      {/* 标签切换 */}
      <div className="mb-4 flex gap-1 border-b">
        {([["general", "系统设置"], ["prompts", "内置提示词管理"]] as [Tab, string][]).map(([t, label]) => (
          <button
            key={t}
            onClick={() => { setTab(t); setError(null); setBrandingMsg(null); setEngineMsg(null); }}
            className={`px-4 py-2 text-sm ${
              tab === t
                ? "border-b-2 border-blue-600 font-medium text-blue-700"
                : "text-gray-500 hover:text-gray-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "prompts" && <PromptsTab />}

      {tab === "general" && (
        <div className="space-y-6">
          {/* 平台品牌配置 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">平台品牌</h2>
            <p className="mb-3 text-xs text-gray-400">自定义左上角显示的平台名称和 Logo。</p>
            <form onSubmit={saveBranding} className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-gray-500">平台名称</label>
                <input
                  value={brandingName}
                  onChange={(e) => setBrandingName(e.target.value)}
                  placeholder="KB-Agent"
                  className="w-full rounded border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500">Logo 图片 URL（留空使用默认缩写）</label>
                <input
                  value={brandingLogo}
                  onChange={(e) => setBrandingLogo(e.target.value)}
                  placeholder="https://example.com/logo.png"
                  className="w-full rounded border px-3 py-2 text-sm"
                />
              </div>
              {branding.logo_url && (
                <img
                  src={branding.logo_url}
                  alt="logo 预览"
                  className="h-10 w-10 rounded object-contain"
                />
              )}
              <button
                type="submit"
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
              >
                保存品牌配置
              </button>
            </form>
            {brandingMsg && <p className="mt-2 text-xs text-green-600">{brandingMsg}</p>}
          </section>

          {/* 引擎配置 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">Agent 引擎</h2>
            <p className="mb-3 text-xs text-gray-400">
              选择处理归类与问答的后端。未实现的选项不可选。
            </p>
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
                    <span className="ml-auto text-xs text-blue-600">当前</span>
                  )}
                </label>
              ))}
              {!engine && <p className="text-sm text-gray-400">加载中…</p>}
            </div>
            {engineMsg && <p className="mt-2 text-xs text-green-600">{engineMsg}</p>}
          </section>

          {/* 域名白名单 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">注册域名白名单</h2>
            <p className="mb-3 text-xs text-gray-400">
              空 = 全拒绝注册。仅列出的域名邮箱可注册（完整域名相等匹配）。
            </p>
            <form onSubmit={addDomain} className="mb-3 flex gap-2">
              <input
                value={domainName}
                onChange={(e) => setDomainName(e.target.value)}
                placeholder="例如 company.com"
                required
                className="flex-1 rounded border px-3 py-2 text-sm"
              />
              <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
                添加域名
              </button>
            </form>
            <ul className="space-y-1 text-sm text-gray-700">
              {domains.map((d) => (
                <li
                  key={d.id}
                  className="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5"
                >
                  <span>{d.domain}</span>
                  <button
                    onClick={() => deleteDomain(d.id)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    删除
                  </button>
                </li>
              ))}
              {domains.length === 0 && (
                <li className="text-gray-400">暂无域名（当前无人可注册）</li>
              )}
            </ul>
          </section>

          {/* 新动态定时 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">新动态定时</h2>
            <p className="mb-3 text-xs text-gray-400">
              当前配置：{FREQ_LABELS[wnFreq] ?? wnFreq}在 {wnHour}:00 UTC 自动生成一次摘要。
            </p>
            <form onSubmit={saveWnSchedule} className="flex flex-wrap items-end gap-3">
              <div>
                <label className="mb-1 block text-xs text-gray-500">生成频率</label>
                <select
                  value={wnFreqInput}
                  onChange={(e) => setWnFreqInput(e.target.value)}
                  className="rounded border px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
                >
                  {(wnFreqOptions.length > 0 ? wnFreqOptions : Object.keys(FREQ_LABELS)).map((f) => (
                    <option key={f} value={f}>{FREQ_LABELS[f] ?? f}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500">触发整点（UTC 0–23）</label>
                <input
                  type="number"
                  min={0}
                  max={23}
                  value={wnHourInput}
                  onChange={(e) => setWnHourInput(Number(e.target.value))}
                  className="w-24 rounded border px-3 py-2 text-sm"
                />
              </div>
              <button
                type="submit"
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
              >
                保存
              </button>
            </form>
            <div className="mt-4 border-t border-gray-100 pt-4">
              <p className="mb-2 text-xs text-gray-400">手动触发一次摘要生成（用于测试）</p>
              <button
                onClick={triggerWnNow}
                disabled={wnTriggering}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                {wnTriggering ? "生成中…" : "立即生成"}
              </button>
              {wnMsg && <p className="mt-2 text-xs text-green-600">{wnMsg}</p>}
            </div>
          </section>

          {/* 引导问题 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">聊天引导问题</h2>
            <p className="mb-3 text-xs text-gray-400">
              新对话空白页展示的快捷问题，点击即发送。每行一条，最多 10 条。
            </p>
            <form onSubmit={saveSuggestedQuestions} className="space-y-3">
              <textarea
                value={sqText}
                onChange={(e) => setSqText(e.target.value)}
                rows={6}
                placeholder={"最近一周有哪些新文档？\n知识库里有哪些产品的文档？\n如何提交技术支持请求？"}
                className="w-full rounded border px-3 py-2 text-sm font-mono leading-relaxed focus:border-blue-400 focus:outline-none"
              />
              <button
                type="submit"
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
              >
                保存引导问题
              </button>
            </form>
            {sqMsg && <p className="mt-2 text-xs text-green-600">{sqMsg}</p>}
          </section>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      )}
    </div>
  );
}
