"use client";

// AI 处理中的气泡：打字动画 + 当前 Agent 工作阶段文字。
export default function ThinkingBubble({ stage }: { stage: string | null }) {
  return (
    <div className="flex flex-row gap-2">
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-xs font-medium text-white"
        aria-hidden
      >
        AI
      </div>
      <div className="flex flex-col items-start">
        <div className="rounded-2xl rounded-tl-sm bg-white px-4 py-3 shadow-sm">
          <span className="flex gap-1" aria-label="正在处理">
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400" />
          </span>
        </div>
        {stage && (
          <p className="mt-1 pl-1 text-xs text-gray-400">{stage}</p>
        )}
      </div>
    </div>
  );
}
