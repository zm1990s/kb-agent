"use client";

import { useState } from "react";

export default function AgentLog({ log }: { log: string[] }) {
  const [open, setOpen] = useState(false);
  if (!log.length) return null;
  return (
    <div className="mt-1 pl-11">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-600"
      >
        <svg
          className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`}
          viewBox="0 0 6 10"
          fill="currentColor"
        >
          <path d="M0 0l6 5-6 5z" />
        </svg>
        查看 Agent 工作日志
      </button>
      {open && (
        <div className="mt-1 max-h-48 overflow-y-auto rounded border border-gray-100 bg-gray-50 p-2 font-mono text-[11px] leading-relaxed text-gray-500">
          {log.map((chunk, i) => (
            <span key={i}>{chunk}</span>
          ))}
        </div>
      )}
    </div>
  );
}
