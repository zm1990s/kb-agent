"use client";

import { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import SaveAsSkillButton from "@/components/chat-plus/SaveAsSkillButton";

interface SessionFile {
  filename: string;
  relpath?: string;
  size: number;
  modified: number;
}

interface Props {
  conversationId: string | null;
  canWriteSkill?: boolean;
}

export interface SessionFilesHandle {
  refresh: () => void;
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// 逐段编码相对路径，保留 / 作为分隔符
function encodePath(p: string): string {
  return p.split("/").map(encodeURIComponent).join("/");
}

const SessionFilesPanel = forwardRef<SessionFilesHandle, Props>(
  function SessionFilesPanel({ conversationId, canWriteSkill }, ref) {
    const t = useTranslations("chatComponents");
    const [open, setOpen] = useState(false);
    const [files, setFiles] = useState<SessionFile[]>([]);
    const [loading, setLoading] = useState(false);
    const boxRef = useRef<HTMLDivElement>(null);

    const load = useCallback(async () => {
      if (!conversationId) {
        setFiles([]);
        return;
      }
      setLoading(true);
      try {
        const data = await api.get<SessionFile[]>(
          `/chat/plus/conversations/${conversationId}/files`
        );
        setFiles(data);
      } catch {
        setFiles([]);
      } finally {
        setLoading(false);
      }
    }, [conversationId]);

    // 暴露给父组件：收到 output_files 后刷新
    useImperativeHandle(ref, () => ({ refresh: load }), [load]);

    useEffect(() => {
      if (open) load();
    }, [open, load]);

    useEffect(() => {
      function handle(e: MouseEvent) {
        if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
      }
      document.addEventListener("mousedown", handle);
      return () => document.removeEventListener("mousedown", handle);
    }, []);

    async function download(f: SessionFile) {
      if (!conversationId) return;
      const token = getToken();
      const res = await fetch(
        `/api/chat/plus/conversations/${conversationId}/files/${encodePath(f.relpath ?? f.filename)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = f.filename;
      a.click();
      URL.revokeObjectURL(url);
    }

    const disabled = !conversationId;

    return (
      <div className="relative" ref={boxRef}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-xs text-gray-600 hover:border-purple-400 hover:text-purple-600 transition-colors disabled:opacity-40"
          title={disabled ? t("sessionFilesDisabled") : t("sessionFiles")}
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
          </svg>
          {t("sessionFiles")}
          {files.length > 0 && (
            <span className="ml-0.5 rounded-full bg-purple-100 px-1.5 py-0.5 text-xs font-medium text-purple-600">
              {files.length}
            </span>
          )}
        </button>

        {open && (
          <div className="absolute bottom-full left-0 z-50 mb-1 w-80 rounded-lg border border-gray-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
              <span className="text-xs font-medium text-gray-700">{t("sessionFiles")}</span>
              <button
                type="button"
                onClick={load}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                {t("refresh")}
              </button>
            </div>
            <div className="max-h-64 overflow-y-auto">
              {loading ? (
                <p className="px-4 py-3 text-xs text-gray-400">{t("loading")}</p>
              ) : files.length === 0 ? (
                <p className="px-4 py-3 text-xs text-gray-400">
                  {t("noFilesYet")}
                </p>
              ) : (
                files.map((f) => (
                  <div
                    key={f.relpath ?? f.filename}
                    className="flex items-center justify-between gap-2 px-3 py-2 hover:bg-gray-50"
                  >
                    <button
                      type="button"
                      onClick={() => download(f)}
                      className="min-w-0 flex flex-1 items-center gap-1.5 text-left"
                      title={f.relpath ?? f.filename}
                    >
                      <svg
                        className="h-3.5 w-3.5 shrink-0 text-gray-400"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                      >
                        <path
                          fillRule="evenodd"
                          d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                          clipRule="evenodd"
                        />
                      </svg>
                      <span className="truncate text-xs text-gray-700">{f.relpath ?? f.filename}</span>
                      <span className="shrink-0 text-xs text-gray-400">{fmtSize(f.size)}</span>
                    </button>
                    <SaveAsSkillButton
                      conversationId={conversationId}
                      filename={f.filename}
                      canWrite={canWriteSkill}
                    />
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    );
  }
);

export default SessionFilesPanel;
