"use client";

import { getToken } from "@/lib/auth";
import SaveAsSkillButton from "@/components/chat-plus/SaveAsSkillButton";

interface OutputFile {
  filename: string;
  relpath?: string;
  storage_key?: string;
  conversation_id?: string;
}

interface Props {
  files: OutputFile[];
  conversationId: string | null;
  canWriteSkill?: boolean;
}

// 逐段编码相对路径，保留 / 作为分隔符（供 {file_path:path} 端点）
function encodePath(p: string): string {
  return p.split("/").map(encodeURIComponent).join("/");
}

export default function OutputFileChip({ files, conversationId, canWriteSkill }: Props) {
  if (!files || files.length === 0) return null;

  async function download(file: OutputFile) {
    const convId = file.conversation_id ?? conversationId;
    if (!convId) return;
    const token = getToken();
    const res = await fetch(
      `/api/chat/plus/conversations/${convId}/files/${encodePath(file.relpath ?? file.filename)}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    );
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = file.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {files.map((f) => (
        <div key={f.filename} className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => download(f)}
            className="flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs text-blue-700 hover:bg-blue-100 transition-colors"
          >
            <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
            <span className="max-w-[200px] truncate" title={f.relpath ?? f.filename}>
              {f.relpath ?? f.filename}
            </span>
          </button>
          <SaveAsSkillButton
            conversationId={f.conversation_id ?? conversationId}
            filename={f.filename}
            canWrite={canWriteSkill}
          />
        </div>
      ))}
    </div>
  );
}
