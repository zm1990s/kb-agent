"use client";

import { useCallback, useEffect, useState } from "react";
import CategoryManager from "@/components/admin/CategoryManager";
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

// 系统设置分区：注册域名白名单 + 引擎（Claude/Codex/OpenClaw）选择。
export default function SystemSettings() {
  const [domains, setDomains] = useState<AllowedDomain[]>([]);
  const [domainName, setDomainName] = useState("");
  const [engine, setEngine] = useState<EngineConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

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

  useEffect(() => {
    loadDomains();
    loadEngine();
  }, [loadDomains, loadEngine]);

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

  async function selectEngine(backend: string) {
    setError(null);
    setSavedMsg(null);
    try {
      const updated = await api.put<EngineConfig>("/settings/engine", { backend });
      setEngine(updated);
      setSavedMsg("引擎已更新");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新失败");
    }
  }

  return (
    <div className="space-y-6">
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
        {savedMsg && <p className="mt-2 text-xs text-green-600">{savedMsg}</p>}
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

      {/* F8：分类体系（从空间管理移来） */}
      <CategoryManager />

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
