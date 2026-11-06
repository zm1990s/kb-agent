"use client";

import { useTranslations } from "next-intl";
import type { AgentRun } from "@/lib/types";
import styles from "./AgentProgress.module.css";

const colors: Record<string, string> = {
  workspace: "#38bdf8", paloalto_kb: "#fb923c", paloalto_live: "#c084fc", paloalto_docs: "#34d399",
};

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
        <div className={styles.heading}><span className={styles.spark} aria-hidden>✦</span>
          <div><h3>{t("agent_flow_title")}</h3><p>{t("agent_flow_subtitle")}</p></div>
        </div>
        <span className={styles.timer}>{elapsed}s</span>
      </div>
      <div className={styles.summary} role="status" aria-live="polite">
        <span className={styles.liveDot} data-active={running > 0} />
        {synthesizing ? t("agent_flow_synthesizing") : t("agent_flow_running", { count: running })}
        <span className={styles.count}>{finished} / {agents.length}</span>
      </div>
      <div className={styles.hub}>{t("agent_flow_dispatch")}</div>
      <div className={styles.trunk} aria-hidden />
      <ul className={styles.branches}>
        {agents.map((agent) => {
          const active = agent.status === "running";
          const done = agent.status === "done";
          const failed = agent.status === "failed";
          const source = agent.source_type ?? "workspace";
          const status = failed ? t("agent_flow_failed") : done
            ? (agent.evidence_count ? t("agent_flow_evidence", { count: agent.evidence_count }) : t("agent_flow_empty"))
            : active ? t("agent_flow_searching") : t("agent_flow_queued");
          return (
            <li key={agent.agent_id} data-state={agent.status}
              style={{ "--agent-color": colors[source] ?? colors.workspace } as React.CSSProperties}
              className={styles.branch}>
              <div className={styles.wire} aria-hidden><i /></div>
              <div className={styles.card}>
                <div className={styles.cardTop}>
                  <span className={styles.icon} aria-hidden>{source === "workspace" ? "▤" : source === "paloalto_live" ? "◎" : source === "paloalto_docs" ? "▥" : "◇"}</span>
                  <span className={styles.stateIcon} aria-hidden>{failed ? "!" : done ? "✓" : active ? "◌" : "·"}</span>
                </div>
                <h4 title={agent.name}>{agent.name}</h4>
                <p className={styles.source}>{t(`source_${source in colors ? source : "workspace"}`)}</p>
                <p className={styles.status}>{status}</p>
                <div className={styles.track} aria-hidden><i /></div>
              </div>
              <div className={styles.returnWire} aria-hidden />
            </li>
          );
        })}
      </ul>
      <div className={styles.merge} data-active={synthesizing}>
        <span aria-hidden>{synthesizing ? "✦" : "◇"}</span>
        {synthesizing ? t("agent_flow_synthesizing") : t("agent_flow_merge")}
      </div>
    </section>
  );
}
