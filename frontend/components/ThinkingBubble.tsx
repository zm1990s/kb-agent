"use client";

import { useTranslations } from "next-intl";

const STEPS = [
  { key: "indexing", labelKey: "stage_indexing" },
  { key: "thinking", labelKey: "stage_thinking" },
  { key: "parsing",  labelKey: "stage_parsing"  },
] as const;

function getStepIndex(stageKey: string | null): number {
  if (!stageKey) return -1;
  const idx = STEPS.findIndex((s) => s.key === stageKey);
  return idx === -1 ? STEPS.length : idx;
}

export default function ThinkingBubble({
  stage,
  stageKey,
}: {
  stage: string | null;
  stageKey?: string | null;
}) {
  const t = useTranslations("chat");
  const activeIdx = getStepIndex(stageKey ?? null);

  return (
    <div className="flex flex-row gap-3">
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white text-xs font-semibold text-gray-700 shadow-sm"
        aria-hidden
      >
        AI
      </div>
      <div className="flex flex-col items-start gap-2">
        <div className="rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 shadow-sm">
          <div className="flex items-center gap-1.5">
            {STEPS.map((step, i) => {
              const done    = i < activeIdx;
              const current = i === activeIdx;
              return (
                <div key={step.key} className="flex items-center gap-1.5">
                  {i > 0 && (
                    <div className={`h-px w-5 transition-colors duration-500 ${done ? "bg-blue-400" : "bg-gray-200"}`} />
                  )}
                  <div className="flex items-center gap-1">
                    <div
                      className={`h-2 w-2 rounded-full transition-all duration-500 ${
                        done    ? "bg-blue-500" :
                        current ? "bg-blue-500 animate-pulse" :
                                  "border border-gray-300 bg-white"
                      }`}
                    />
                    <span
                      className={`text-xs transition-colors duration-300 ${
                        done    ? "text-blue-500" :
                        current ? "text-blue-600 font-medium" :
                                  "text-gray-400"
                      }`}
                    >
                      {t(step.labelKey)}
                    </span>
                  </div>
                </div>
              );
            })}
            {activeIdx < STEPS.length && (
              <div className="ml-2 flex gap-1 items-center" aria-label={t("preparing")}>
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
              </div>
            )}
          </div>
        </div>
        {stage && (
          <p className="pl-1 text-xs text-gray-400">{stage}</p>
        )}
      </div>
    </div>
  );
}
