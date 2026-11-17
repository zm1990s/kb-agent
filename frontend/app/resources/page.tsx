"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import NavBar from "@/components/NavBar";
import { api, ApiError } from "@/lib/api";
import { getToken, isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";
import type { Resource } from "@/lib/types";

type ResourceType = "url" | "html";

export default function ResourcesPage() {
  const t = useTranslations("resources");
  const ready = useAuthGuard("resources");
  const admin = isAdmin();

  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form state
  const [showAdd, setShowAdd] = useState(false);
  const [addType, setAddType] = useState<ResourceType>("url");
  const [addTitle, setAddTitle] = useState("");
  const [addDesc, setAddDesc] = useState("");
  const [addUrl, setAddUrl] = useState("");
  const [addFile, setAddFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Edit state: id of card being edited + field values
  const [editId, setEditId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editFile, setEditFile] = useState<File | null>(null);
  const editFileRef = useRef<HTMLInputElement>(null);
  const [editSaving, setEditSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<Resource[]>("/resources");
      setResources(data);
    } catch {
      setResources([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready) load();
  }, [ready, load]);

  if (!ready) return null;

  function resetForm() {
    setAddTitle("");
    setAddDesc("");
    setAddUrl("");
    setAddFile(null);
    setAddType("url");
    if (fileRef.current) fileRef.current.value = "";
  }

  async function handleAdd() {
    setError(null);
    if (!addTitle.trim()) { setError(t("errNoTitle")); return; }
    if (addType === "url" && !addUrl.trim()) { setError(t("errNoUrl")); return; }
    if (addType === "html" && !addFile) { setError(t("errNoFile")); return; }
    setSaving(true);
    try {
      if (addType === "url") {
        await api.post("/resources", {
          type: "url",
          title: addTitle.trim(),
          description: addDesc.trim() || null,
          url: addUrl.trim(),
        });
      } else {
        const form = new FormData();
        form.append("file", addFile!);
        form.append("title", addTitle.trim());
        if (addDesc.trim()) form.append("description", addDesc.trim());
        await api.upload("/resources/upload", form);
      }
      resetForm();
      setShowAdd(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  function startEdit(r: Resource) {
    setEditId(r.id);
    setEditTitle(r.title);
    setEditDesc(r.description ?? "");
    setEditUrl(r.url ?? "");
    setEditFile(null);
    if (editFileRef.current) editFileRef.current.value = "";
    setError(null);
  }

  async function handleEdit(id: string, isHtml: boolean) {
    if (!editTitle.trim()) { setError(t("errNoTitle")); return; }
    setEditSaving(true);
    setError(null);
    try {
      let updated = await api.patch<Resource>(`/resources/${id}`, {
        title: editTitle.trim(),
        description: editDesc.trim() || null,
        url: !isHtml ? (editUrl.trim() || null) : null,
      });
      // If a new HTML file was selected, upload it
      if (isHtml && editFile) {
        const form = new FormData();
        form.append("file", editFile);
        updated = await api.upload<Resource>(`/resources/${id}/file`, form);
      }
      setResources((prev) => prev.map((r) => (r.id === id ? updated : r)));
      setEditId(null);
      setEditFile(null);
      if (editFileRef.current) editFileRef.current.value = "";
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm(t("deleteConfirm"))) return;
    setError(null);
    try {
      await api.del(`/resources/${id}`);
      setResources((prev) => prev.filter((r) => r.id !== id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("deleteFailed"));
    }
  }

  async function openResource(r: Resource) {
    if (r.type === "url" && r.url) {
      window.open(r.url, "_blank", "noopener,noreferrer");
      return;
    }
    // HTML: fetch blob then open in new tab
    try {
      const token = getToken();
      const res = await fetch(`/api/resources/${r.id}/file`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        let msg = t("openFailed");
        try { const d = await res.json(); if (typeof d?.detail === "string") msg = d.detail; } catch { /* ignore */ }
        setError(msg);
        return;
      }
      const html = await res.text();
      const blob = new Blob([html], { type: "text/html" });
      const blobUrl = URL.createObjectURL(blob);
      const win = window.open(blobUrl, "_blank", "noopener,noreferrer");
      // revoke after the new tab has had time to load
      setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
      if (!win) setError(t("popupBlocked"));
    } catch {
      setError(t("openFailed"));
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <NavBar />
      <main className="mx-auto w-full max-w-5xl flex-1 p-6">
        <div className="mb-5 flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-800">{t("title")}</h1>
          {admin && (
            <button
              onClick={() => { setShowAdd((v) => !v); setError(null); }}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              {showAdd ? t("cancel") : t("addResource")}
            </button>
          )}
        </div>

        {/* Add form */}
        {showAdd && admin && (
          <div className="mb-6 rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold text-gray-700">{t("addResource")}</h2>

            {/* Type selector */}
            <div className="mb-3 flex gap-3">
              {(["url", "html"] as ResourceType[]).map((tp) => (
                <button
                  key={tp}
                  type="button"
                  onClick={() => setAddType(tp)}
                  className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-colors ${
                    addType === tp
                      ? "border-blue-600 bg-blue-50 text-blue-700"
                      : "border-gray-300 text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {tp === "url" ? t("typeUrl") : t("typeHtml")}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <input
                value={addTitle}
                onChange={(e) => setAddTitle(e.target.value)}
                placeholder={t("titlePlaceholder")}
                className="rounded-lg border px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
              <input
                value={addDesc}
                onChange={(e) => setAddDesc(e.target.value)}
                placeholder={t("descPlaceholder")}
                className="rounded-lg border px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
              {addType === "url" ? (
                <input
                  value={addUrl}
                  onChange={(e) => setAddUrl(e.target.value)}
                  placeholder={t("urlPlaceholder")}
                  className="rounded-lg border px-3 py-2 text-sm outline-none focus:border-blue-500 sm:col-span-2"
                />
              ) : (
                <div className="sm:col-span-2">
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".html"
                    onChange={(e) => setAddFile(e.target.files?.[0] ?? null)}
                    className="text-sm text-gray-600"
                  />
                  <p className="mt-1 text-xs text-gray-400">{t("htmlHint")}</p>
                </div>
              )}
            </div>

            {error && <p className="mt-3 text-sm text-red-500">{error}</p>}

            <div className="mt-4 flex justify-end">
              <button
                onClick={handleAdd}
                disabled={saving}
                className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
              >
                {saving ? t("saving") : t("save")}
              </button>
            </div>
          </div>
        )}

        {!showAdd && error && <p className="mb-4 text-sm text-red-500">{error}</p>}

        {loading && (
          <p className="text-sm text-gray-400">{t("loading")}</p>
        )}

        {!loading && resources.length === 0 && (
          <div className="rounded-xl border border-dashed bg-white px-6 py-12 text-center text-sm text-gray-400">
            {t("empty")}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {resources.map((r) => (
            <div
              key={r.id}
              className="flex flex-col rounded-xl border bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
            >
              {/* Type badge */}
              <div className="mb-2 flex items-start justify-between gap-2">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                    r.type === "url"
                      ? "bg-blue-100 text-blue-700"
                      : "bg-purple-100 text-purple-700"
                  }`}
                >
                  {r.type === "url" ? "URL" : "HTML"}
                </span>
                {admin && (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => editId === r.id ? setEditId(null) : startEdit(r)}
                      className="text-gray-300 hover:text-blue-500"
                      title={t("edit")}
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125" />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleDelete(r.id)}
                      className="text-gray-300 hover:text-red-500"
                      title={t("delete")}
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>

              {/* Inline edit form */}
              {admin && editId === r.id ? (
                <div className="mt-2 space-y-2">
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    placeholder={t("titlePlaceholder")}
                    className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none focus:border-blue-500"
                  />
                  <input
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    placeholder={t("descPlaceholder")}
                    className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none focus:border-blue-500"
                  />
                  {r.type === "url" && (
                    <input
                      value={editUrl}
                      onChange={(e) => setEditUrl(e.target.value)}
                      placeholder={t("urlPlaceholder")}
                      className="w-full rounded-lg border px-3 py-1.5 text-sm outline-none focus:border-blue-500"
                    />
                  )}
                  {r.type === "html" && (
                    <div>
                      <label className="mb-1 block text-xs text-gray-500">{t("replaceFileLabel")}</label>
                      <input
                        ref={editFileRef}
                        type="file"
                        accept=".html"
                        onChange={(e) => setEditFile(e.target.files?.[0] ?? null)}
                        className="text-xs text-gray-600"
                      />
                      {editFile && (
                        <p className="mt-0.5 text-xs text-blue-600">{editFile.name}</p>
                      )}
                    </div>
                  )}
                  {error && <p className="text-xs text-red-500">{error}</p>}
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setEditId(null)}
                      className="rounded-lg border px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
                    >
                      {t("cancel")}
                    </button>
                    <button
                      onClick={() => handleEdit(r.id, r.type === "html")}
                      disabled={editSaving}
                      className="rounded-lg bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-40"
                    >
                      {editSaving ? t("saving") : t("save")}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <h3 className="mb-1 line-clamp-2 text-sm font-semibold text-gray-800">{r.title}</h3>
                  {r.description && (
                    <p className="mb-3 line-clamp-2 flex-1 text-xs text-gray-500">{r.description}</p>
                  )}
                  <div className="mt-auto pt-3">
                    <button
                      onClick={() => openResource(r)}
                      className="w-full rounded-lg bg-gray-100 py-1.5 text-xs font-medium text-gray-700 hover:bg-blue-50 hover:text-blue-700"
                    >
                      {t("open")} ↗
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
