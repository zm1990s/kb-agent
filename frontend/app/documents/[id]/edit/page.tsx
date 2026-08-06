"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import NavBar from "@/components/NavBar";
import CaseEditor, { type CaseEditorHandle } from "@/components/CaseEditor";
import { api, ApiError } from "@/lib/api";
import { useAuthGuard } from "@/lib/useAuthGuard";

export default function DocumentEditPage() {
  const t = useTranslations("documents");
  const tCase = useTranslations("caseEntry");
  const ready = useAuthGuard("documents");
  const params = useParams();
  const router = useRouter();
  const docId = params.id as string;
  const editorRef = useRef<CaseEditorHandle>(null);

  const [title, setTitle] = useState("");
  const [initialHtml, setInitialHtml] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState(false);

  useEffect(() => {
    if (!ready || !docId) return;
    api
      .get<{ html: string; title: string }>(`/documents/${docId}/html`)
      .then(({ html, title: docTitle }) => {
        setTitle(docTitle);
        setInitialHtml(html);
      })
      .catch((e) => {
        setLoadError(e instanceof ApiError ? e.message : t("editLoadFailed"));
      })
      .finally(() => setLoading(false));
  }, [ready, docId, t]);

  if (!ready) return null;

  async function save() {
    setSaveError(null);
    setSavedMsg(false);
    const editor = editorRef.current;
    if (!editor) return;
    if (!title.trim()) {
      setSaveError(tCase("errNoTitle"));
      return;
    }
    setSaving(true);
    try {
      await api.post(`/documents/${docId}/edit-save`, {
        title: title.trim(),
        content_json: editor.getJSON(),
        content_html: editor.getHTML(),
      });
      setSavedMsg(true);
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : t("editSave") + " 失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <NavBar />
      <main className="mx-auto w-full max-w-4xl flex-1 p-4">
        <div className="mb-4 flex items-center gap-2 text-sm text-gray-500">
          <Link href="/documents" className="hover:text-gray-700 underline">
            {t("editBackToList")}
          </Link>
          <span>/</span>
          <span className="text-gray-700">{t("action_edit")}</span>
        </div>

        {loadError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {loadError}
          </div>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={tCase("titlePlaceholder")}
                className="flex-1 min-w-[200px] rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={save}
                disabled={saving || loading}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
              >
                {saving ? t("editSaving") : t("editSave")}
              </button>
              <button
                type="button"
                onClick={() => router.push("/documents")}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                {t("editBackToList")}
              </button>
            </div>

            {loading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-8 rounded bg-gray-200" />
                <div className="h-64 rounded bg-gray-200" />
              </div>
            ) : (
              <CaseEditor
                ref={editorRef}
                initialContent={initialHtml}
                onImageError={() => setSaveError(tCase("errImageTooLarge"))}
              />
            )}

            {saveError && <p className="mt-3 text-sm text-red-500">{saveError}</p>}
            {savedMsg && (
              <div className="mt-3 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
                {t("editSaved")}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
