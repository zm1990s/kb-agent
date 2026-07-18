"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";

interface AttachedFile {
  storage_key: string;
  filename: string;
  size?: number;
}

interface Props {
  files: AttachedFile[];
  onChange: (files: AttachedFile[]) => void;
}

export default function FileAttachPanel({ files, onChange }: Props) {
  const t = useTranslations("chatComponents");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(fileList: FileList) {
    setError(null);
    const toUpload = Array.from(fileList);
    setUploading(true);
    try {
      const results: AttachedFile[] = [];
      for (const file of toUpload) {
        const form = new FormData();
        form.append("file", file);
        const res = await api.upload<AttachedFile>(`/chat/plus/upload`, form);
        results.push(res);
      }
      onChange([...files, ...results]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("attachFailed"));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function remove(key: string) {
    onChange(files.filter((f) => f.storage_key !== key));
  }

  if (files.length === 0 && !uploading) {
    return (
      <div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-xs text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors"
          title={t("attach")}
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
          </svg>
          {t("attach")}
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
        {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {files.map((f) => (
        <div
          key={f.storage_key}
          className="flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700"
        >
          <svg className="h-3 w-3 shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" />
          </svg>
          <span className="max-w-[100px] truncate">{f.filename}</span>
          <button
            type="button"
            onClick={() => remove(f.storage_key)}
            className="ml-0.5 text-blue-400 hover:text-blue-700"
          >
            ×
          </button>
        </div>
      ))}
      {uploading && (
        <span className="text-xs text-gray-400">{t("uploadingFile")}</span>
      )}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className="rounded-full border border-dashed border-gray-300 px-2 py-1 text-xs text-gray-400 hover:border-blue-400 hover:text-blue-500"
      >
        {t("add")}
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
