"use client";

import { useTranslations } from "next-intl";
import type { AgentRun } from "@/lib/types";
import styles from "./AgentProgress.module.css";

export default function AgentProgress({ agents, stageKey, elapsed }: {
  agents: AgentRun[]; stageKey: string | null; elapsed: number;
}) {
  const t = useTranslations("chat");
  const finished = agents.filter((a) => a.status === "done" || a.status === "failed").length;
  const synthesizing = stageKey === "thinking" || stageKey === "parsing" || stageKey === "done";
  const running = agents.filter((a) => a.status === "running").length;
  return (
    <section aria-label={t("agent_flow_title")} className={styles.panel}>
      <div className={styles.header}>
        <h3>{t("agent_flow_title")}</h3>
        <span className={styles.timer}>{elapsed}s</span>
      </div>
      <div className={styles.map}>
        <div className={styles.root}>
          {t(synthesizing ? "stage_thinking" : "stage_indexing")}
        </div>
        <ul className={styles.branches}>
          {agents.map((agent) => {
            const active = agent.status === "running";
            const done = agent.status === "done";
            const failed = agent.status === "failed";
            const status = failed ? t("agent_flow_failed") : done
              ? (agent.evidence_count ? t("agent_flow_evidence", { count: agent.evidence_count }) : t("agent_flow_empty"))
              : active ? t("agent_flow_searching") : t("agent_flow_queued");
            return (
              <li key={agent.agent_id} data-state={agent.status} className={styles.branch}>
                <div className={styles.node}>
                  <span className={styles.indicator} aria-hidden>{failed ? "!" : done ? "✓" : ""}</span>
                  <h4>{agent.name}</h4>
                  <span className={styles.status}>{status}</span>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      <div className={styles.summary} role="status" aria-live="polite">
        <span>{synthesizing ? t("agent_flow_synthesizing") : running > 0
          ? t("agent_flow_running", { count: running }) : t("preparing")}</span>
        <span className={styles.count}>{finished} / {agents.length}</span>
      </div>
    </section>
  );
}
