"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Image from "next/image";
import AIEngineSettings from "@/components/admin/AIEngineSettings";
import PromptsTab from "@/components/admin/PromptsTab";
import UserAdmin from "@/components/admin/UserAdmin";
import WorkspaceAdmin from "@/components/admin/WorkspaceAdmin";
import { api, ApiError } from "@/lib/api";
import type { AllowedDomain } from "@/lib/types";

interface Branding {
  name: string;
  logo_url: string;
}

type Tab = "workspaces" | "users" | "general" | "prompts" | "ai_engine";

interface Props {
  // null = admin（全部可见）；Record = 普通用户权限表
  perms?: Record<string, string> | null;
}

export default function SystemSettings({ perms }: Props) {
  const t = useTranslations("settings");
  const isAdmin = perms === undefined || perms === null;
  const canSee = (module: string) => isAdmin || (perms?.[module] ?? "none") !== "none";

  const defaultTab: Tab =
    canSee("workspaces") ? "workspaces"
    : canSee("users") ? "users"
    : "general";

  const [tab, setTab] = useState<Tab>(defaultTab);
  const [domains, setDomains] = useState<AllowedDomain[]>([]);
  const [domainName, setDomainName] = useState("");
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
  const [siteBaseUrl, setSiteBaseUrl] = useState("");
  const [siteBaseUrlInput, setSiteBaseUrlInput] = useState("");
  const [siteBaseUrlMsg, setSiteBaseUrlMsg] = useState<string | null>(null);
  const [requireEmailVerification, setRequireEmailVerification] = useState(false);
  const [emailVerificationMsg, setEmailVerificationMsg] = useState<string | null>(null);

  const loadDomains = useCallback(async () => {
    try {
      setDomains(await api.get<AllowedDomain[]>("/auth/allowed-domains"));
    } catch {
      setDomains([]);
    }
  }, []);

  const loadBranding = useCallback(async () => {
    try {
      const b = await api.get<Branding>("/settings/branding");
      setBranding(b);
      setBrandingName(b.name);
      setBrandingLogo(b.logo_url);
    } catch { /* 非管理员读不到也没关系 */ }
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

  const loadEmailVerification = useCallback(async () => {
    try {
      const d = await api.get<{ require_email_verification: boolean; site_base_url: string }>(
        "/settings/email-verification"
      );
      setRequireEmailVerification(d.require_email_verification);
      setSiteBaseUrl(d.site_base_url);
      setSiteBaseUrlInput(d.site_base_url);
    } catch { /* 非 admin 正常 */ }
  }, []);

  useEffect(() => {
    loadDomains();
    loadBranding();
    loadWnSchedule();
    loadSuggestedQuestions();
    loadEmailVerification();
  }, [loadDomains, loadBranding, loadWnSchedule, loadSuggestedQuestions, loadEmailVerification]);

  async function addDomain(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/auth/allowed-domains", { domain: domainName });
      setDomainName("");
      await loadDomains();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("add_failed"));
    }
  }

  async function deleteDomain(id: string) {
    setError(null);
    try {
      await api.del(`/auth/allowed-domains/${id}`);
      await loadDomains();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("delete_failed"));
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
      setBrandingMsg(t("branding_saved"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
    }
  }

  const FREQ_LABELS: Record<string, string> = {
    daily: t("freq_daily"),
    weekly: t("freq_weekly"),
    biweekly: t("freq_biweekly"),
    monthly: t("freq_monthly"),
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
      setWnMsg(t("whatsnew_saved", { freq: FREQ_LABELS[d.frequency] ?? d.frequency, hour: d.hour }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
    }
  }

  async function triggerWnNow() {
    setWnTriggering(true);
    setWnMsg(null);
    setError(null);
    try {
      await api.post("/whatsnew/trigger", {});
      setWnMsg(t("whatsnew_trigger_success"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("trigger_failed"));
    } finally {
      setWnTriggering(false);
    }
  }

  async function saveSiteBaseUrl(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSiteBaseUrlMsg(null);
    try {
      const d = await api.put<{ site_base_url: string }>("/settings/email-verification", {
        site_base_url: siteBaseUrlInput.trim(),
      });
      setSiteBaseUrl(d.site_base_url);
      setSiteBaseUrlInput(d.site_base_url);
      setSiteBaseUrlMsg(t("site_base_url_saved"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
    }
  }

  async function toggleEmailVerification(enabled: boolean) {
    setError(null);
    setEmailVerificationMsg(null);
    try {
      await api.put("/settings/email-verification", { require_email_verification: enabled });
      setRequireEmailVerification(enabled);
      setEmailVerificationMsg(enabled ? t("email_verification_enabled") : t("email_verification_disabled"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
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
      setSqMsg(t("suggested_saved", { count: updated.questions.length }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("save_failed"));
    }
  }

  return (
    <div>
      {/* 标签切换：按权限过滤 */}
      <div className="mb-4 flex gap-1 border-b">
        {([
          ["workspaces", t("tab_workspaces")],
          ["users", t("tab_users")],
          ["general", t("tab_general")],
          ["prompts", t("tab_prompts")],
          ["ai_engine", t("tab_ai_engine")],
        ] as [Tab, string][])
          .filter(([tabKey]) => {
            if (tabKey === "workspaces") return canSee("workspaces");
            if (tabKey === "users") return canSee("users");
            return isAdmin; // general / prompts / ai_engine 仅管理员
          })
          .map(([tabKey, label]) => (
            <button
              key={tabKey}
              onClick={() => { setTab(tabKey); setError(null); setBrandingMsg(null); }}
              className={`px-4 py-2 text-sm ${
                tab === tabKey
                  ? "border-b-2 border-blue-600 font-medium text-blue-700"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {label}
            </button>
          ))}
      </div>

      {tab === "workspaces" && <WorkspaceAdmin />}
      {tab === "users" && <UserAdmin />}
      {tab === "prompts" && <PromptsTab />}
      {tab === "ai_engine" && <AIEngineSettings />}

      {tab === "general" && (
        <div className="space-y-6">
          {/* 平台品牌配置 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">{t("branding_title")}</h2>
            <p className="mb-3 text-xs text-gray-400">{t("branding_desc")}</p>
            <form onSubmit={saveBranding} className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-gray-500">{t("branding_name_label")}</label>
                <input
                  value={brandingName}
                  onChange={(e) => setBrandingName(e.target.value)}
                  placeholder="KB-Agent"
                  className="w-full rounded border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-500">{t("branding_logo_label")}</label>
                <input
                  value={brandingLogo}
                  onChange={(e) => setBrandingLogo(e.target.value)}
                  placeholder="https://example.com/logo.png"
                  className="w-full rounded border px-3 py-2 text-sm"
                />
              </div>
              {branding.logo_url && (
                <Image
                  src={branding.logo_url}
                  alt="logo preview"
                  width={40}
                  height={40}
                  className="h-10 w-10 rounded object-contain"
                  unoptimized
                />
              )}
              <button
                type="submit"
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
              >
                {t("branding_save")}
              </button>
            </form>
            {brandingMsg && <p className="mt-2 text-xs text-green-600">{brandingMsg}</p>}
          </section>

          {/* 域名白名单 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">{t("domain_title")}</h2>
            <p className="mb-3 text-xs text-gray-400">{t("domain_desc")}</p>
            <form onSubmit={addDomain} className="mb-3 flex gap-2">
              <input
                value={domainName}
                onChange={(e) => setDomainName(e.target.value)}
                placeholder={t("domain_placeholder")}
                required
                className="flex-1 rounded border px-3 py-2 text-sm"
              />
              <button className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
                {t("domain_add")}
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
                    {t("domain_delete")}
                  </button>
                </li>
              ))}
              {domains.length === 0 && (
                <li className="text-gray-400">{t("domain_none")}</li>
              )}
            </ul>
          </section>

          {/* 新动态定时 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">{t("whatsnew_title")}</h2>
            <p className="mb-3 text-xs text-gray-400">
              {t("whatsnew_current", { freq: FREQ_LABELS[wnFreq] ?? wnFreq, hour: wnHour })}
            </p>
            <form onSubmit={saveWnSchedule} className="flex flex-wrap items-end gap-3">
              <div>
                <label className="mb-1 block text-xs text-gray-500">{t("whatsnew_freq_label")}</label>
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
                <label className="mb-1 block text-xs text-gray-500">{t("whatsnew_hour_label")}</label>
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
                {t("whatsnew_save")}
              </button>
            </form>
            <div className="mt-4 border-t border-gray-100 pt-4">
              <p className="mb-2 text-xs text-gray-400">{t("whatsnew_trigger_label")}</p>
              <button
                onClick={triggerWnNow}
                disabled={wnTriggering}
                className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                {wnTriggering ? t("whatsnew_triggering") : t("whatsnew_trigger")}
              </button>
              {wnMsg && <p className="mt-2 text-xs text-green-600">{wnMsg}</p>}
            </div>
          </section>

          {/* 引导问题 */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">{t("suggested_title")}</h2>
            <p className="mb-3 text-xs text-gray-400">{t("suggested_desc")}</p>
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
                {t("suggested_save")}
              </button>
            </form>
            {sqMsg && <p className="mt-2 text-xs text-green-600">{sqMsg}</p>}
          </section>

          {/* 邮箱验证开关（含站点基础 URL 子菜单） */}
          <section className="rounded border bg-white p-4">
            <h2 className="mb-1 text-sm font-medium">{t("email_verification_title")}</h2>
            <p className="mb-3 text-xs text-gray-400">{t("email_verification_desc")}</p>
            <label className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={requireEmailVerification}
                onChange={(e) => toggleEmailVerification(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 accent-blue-600"
              />
              <span className="text-sm text-gray-700">
                {requireEmailVerification ? t("email_verification_on") : t("email_verification_off")}
              </span>
            </label>
            {emailVerificationMsg && <p className="mt-2 text-xs text-green-600">{emailVerificationMsg}</p>}

            {/* 站点基础 URL */}
            <div className="mt-4 rounded border border-gray-100 bg-gray-50 p-3">
              <h3 className="mb-1 text-xs font-medium text-gray-700">{t("site_base_url_title")}</h3>
              <p className="mb-3 text-xs text-gray-400">{t("site_base_url_desc")}</p>
              <form onSubmit={saveSiteBaseUrl} className="flex gap-2">
                <input
                  type="url"
                  value={siteBaseUrlInput}
                  onChange={(e) => setSiteBaseUrlInput(e.target.value)}
                  placeholder="https://kb.example.com"
                  className="flex-1 rounded border bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
                />
                <button
                  type="submit"
                  className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
                >
                  {t("site_base_url_save")}
                </button>
              </form>
              {siteBaseUrl && (
                <p className="mt-2 text-xs text-gray-400">
                  {t("site_base_url_current")}: <code className="text-gray-600">{siteBaseUrl}</code>
                </p>
              )}
              {siteBaseUrlMsg && <p className="mt-2 text-xs text-green-600">{siteBaseUrlMsg}</p>}
            </div>
          </section>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      )}
    </div>
  );
}
