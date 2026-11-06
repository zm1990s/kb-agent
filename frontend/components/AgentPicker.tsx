"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import type { RetrievalAgent } from "@/lib/types";

export default function AgentPicker({ value, onChange, disabled }: {
  value: string[] | null;
  onChange: (ids: string[] | null) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("chat");
  const [agents, setAgents] = useState<RetrievalAgent[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api.get<RetrievalAgent[]>("/chat/agents").then((items) => {
      if (active) setAgents(items);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, []);
  if (disabled) return null;
  return (
    <details className="relative text-sm">
      <summary className="cursor-pointer rounded border border-gray-200 px-3 py-1.5 text-gray-600">
        {t("agent_capabilities")} · {value === null ? t("agent_auto") : value.length}
      </summary>
      <div className="absolute left-0 z-20 mt-2 max-h-80 w-80 overflow-y-auto rounded-lg border bg-white p-3 shadow-lg">
        <p className="mb-2 text-xs text-gray-500">{t("agent_hint")}</p>
        {failed ? <p className="text-xs text-red-600">{t("load_failed")}</p> : <>
          <button type="button" onClick={() => onChange(null)} className="mb-2 text-xs text-blue-600">
            {t("agent_reset")}
          </button>
          {agents.map((agent) => <label key={agent.id} className="flex gap-2 rounded p-2 hover:bg-gray-50">
            <input type="checkbox" checked={value === null || value.includes(agent.id)}
              onChange={(event) => {
                const ids = value ?? agents.map((item) => item.id);
                onChange(event.target.checked ? [...new Set([...ids, agent.id])]
                  : ids.filter((id) => id !== agent.id));
              }} />
            <span><span className="block">{agent.name}</span>
              <span className="block text-xs text-gray-500">{agent.description}</span></span>
          </label>)}
        </>}
      </div>
    </details>
  );
}
