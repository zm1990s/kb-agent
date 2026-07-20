"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import NavBar from "@/components/NavBar";
import CaseEditor, { type CaseEditorHandle } from "@/components/CaseEditor";
import { api, ApiError } from "@/lib/api";
import { useAuthGuard } from "@/lib/useAuthGuard";

interface CaseWorkspace {
  workspace_id: string | null;
  workspace_name: string | null;
}

export default function CaseEntryPage() {
  const t = useTranslations("caseEntry");
  const ready = useAuthGuard("documents");
  const editorRef = useRef<CaseEditorHandle>(null);

  const [title, setTitle] = useState("");
  const [format, setFormat] = useState<"docx" | "pdf">("docx");
  const [defaultWs, setDefaultWs] = useState<CaseWorkspace | null>(null);
  const [wsLoaded, setWsLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    api
      .get<CaseWorkspace>("/settings/case-default-workspace")
      .then((w) => setDefaultWs(w))
      .catch(() => setDefaultWs({ workspace_id: null, workspace_name: null }))
      .finally(() => setWsLoaded(true));
  }, [ready]);

  if (!ready) return null;

  const notConfigured = wsLoaded && !defaultWs?.workspace_id;

  async function save() {
    setError(null);
    setSavedId(null);
    const editor = editorRef.current;
    if (!editor) return;
    if (!title.trim()) {
      setError(t("errNoTitle"));
      return;
    }
    if (editor.isEmpty()) {
      setError(t("errEmpty"));
      return;
    }
    setSaving(true);
    try {
      const doc = await api.post<{ id: string }>("/cases", {
        title: title.trim(),
        format,
        content_json: editor.getJSON(),
        content_html: editor.getHTML(),
      });
      setSavedId(doc.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <NavBar />
      <main className="mx-auto w-full max-w-4xl flex-1 p-4">
        <h1 className="mb-4 text-lg font-semibold">{t("title")}</h1>

        {notConfigured && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
            {t("notConfigured")}
          </div>
        )}

        <div className="mb-3 flex flex-wrap items-center gap-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t("titlePlaceholder")}
            className="flex-1 min-w-[200px] rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500"
          />
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as "docx" | "pdf")}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="docx">{t("formatDocx")}</option>
            <option value="pdf">{t("formatPdf")}</option>
          </select>
          <button
            type="button"
            onClick={save}
            disabled={saving || notConfigured}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
          >
            {saving ? t("saving") : t("save")}
          </button>
        </div>

        {defaultWs?.workspace_name && (
          <p className="mb-2 text-xs text-gray-400">
            {t("saveTargetLabel")}
            <span className="font-medium text-gray-600">{defaultWs.workspace_name}</span>
          </p>
        )}

        <CaseEditor ref={editorRef} onImageError={() => setError(t("errImageTooLarge"))} />

        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
        {savedId && (
          <div className="mt-3 flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
            <span>{t("saved")}</span>
            <Link href="/documents" className="font-medium underline hover:text-green-800">
              {t("goDocuments")}
            </Link>
          </div>
        )}
      </main>
    </div>
  );
}
