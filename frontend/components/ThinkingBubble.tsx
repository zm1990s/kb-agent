"use client";

export default function ThinkingBubble({ stage }: { stage: string | null }) {
  return (
    <div className="flex flex-row gap-3">
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white text-xs font-semibold text-gray-700 shadow-sm"
        aria-hidden
      >
        AI
      </div>
      <div className="flex flex-col items-start gap-1.5">
        <div className="rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 shadow-sm">
          <span className="flex gap-1.5 items-center" aria-label="正在处理">
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400 [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-gray-400" />
          </span>
        </div>
        {stage && (
          <p className="pl-1 text-xs text-gray-400">{stage}</p>
        )}
      </div>
    </div>
  );
}
