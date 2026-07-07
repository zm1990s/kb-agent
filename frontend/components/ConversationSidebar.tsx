"use client";

import type { ConversationSummary } from "@/lib/types";

interface Props {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

// 会话侧边栏：新建会话 + 会话列表。
export default function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
}: Props) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r bg-white">
      <button
        onClick={onNew}
        className="m-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        + 新建会话
      </button>
      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 && (
          <p className="px-3 py-2 text-xs text-gray-400">暂无会话</p>
        )}
        {conversations.map((c, i) => (
          <button
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={`block w-full truncate px-3 py-2 text-left text-sm ${
              c.id === activeId
                ? "bg-blue-50 text-blue-700"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            会话 {conversations.length - i} ·{" "}
            {new Date(c.created_at).toLocaleDateString()}
          </button>
        ))}
      </div>
    </aside>
  );
}
