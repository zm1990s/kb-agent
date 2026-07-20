"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import NavBar from "@/components/NavBar";
import { api, ApiError } from "@/lib/api";
import { getToken, isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";

interface Skill {
  id: string;
  name: string;
  description: string | null;
  content: string;
  category: string | null;
  tags: string[];
  is_public: boolean;
  has_bundle?: boolean;
  created_by: string | null;
  created_by_email?: string | null;
  created_at: string;
  updated_at: string;
}

export default function SkillsPage() {
  const t = useTranslations("skillsHub");
  const ready = useAuthGuard("skills");
  const admin = isAdmin();
  const [canWrite, setCanWrite] = useState(false);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);

  // 详情弹窗
  const [detail, setDetail] = useState<Skill | null>(null);

  // 创建/编辑抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Skill | null>(null);
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formCategory, setFormCategory] = useState("");
  const [formTags, setFormTags] = useState("");
  const [formContent, setFormContent] = useState("");
  const [formPublic, setFormPublic] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  // 上传
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      if (category) params.set("category", category);
      const qs = params.toString();
      const data = await api.get<Skill[]>(`/skills${qs ? `?${qs}` : ""}`);
      setSkills(data);
    } catch {
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, [search, category]);

  // 搜索防抖
  useEffect(() => {
    const timer = setTimeout(loadSkills, 250);
    return () => clearTimeout(timer);
  }, [loadSkills]);

  // 是否有 skills:write（只读用户隐藏上传/新建/编辑/删除；后端仍是唯一防线）
  useEffect(() => {
    if (admin) {
      setCanWrite(true);
      return;
    }
    api
      .get<Record<string, string>>("/auth/my-permissions")
      .then((perms) => setCanWrite(perms.skills === "write"))
      .catch(() => setCanWrite(false));
  }, [admin]);

  // 全量分类列表（从当前结果聚合；分类筛选下仍展示所有已知分类）
  const [allCategories, setAllCategories] = useState<string[]>([]);
  useEffect(() => {
    // 仅在无筛选时刷新分类全集
    if (!search.trim() && !category) {
      const cats = Array.from(
        new Set(skills.map((s) => s.category).filter((c): c is string => !!c))
      ).sort();
      setAllCategories(cats);
    }
  }, [skills, search, category]);

  const stats = useMemo(() => {
    const total = skills.length;
    const catCount = new Set(skills.map((s) => s.category).filter(Boolean)).size;
    const latest = skills.reduce<string | null>((acc, s) => {
      if (!acc || s.updated_at > acc) return s.updated_at;
      return acc;
    }, null);
    return { total, catCount, latest };
  }, [skills]);

  function openCreate() {
    setEditing(null);
    setFormName("");
    setFormDesc("");
    setFormCategory("");
    setFormTags("");
    setFormContent("");
    setFormPublic(true);
    setMsg("");
    setDrawerOpen(true);
  }

  function openEdit(s: Skill) {
    setEditing(s);
    setFormName(s.name);
    setFormDesc(s.description ?? "");
    setFormCategory(s.category ?? "");
    setFormTags((s.tags ?? []).join(", "));
    setFormContent(s.content);
    setFormPublic(s.is_public);
    setMsg("");
    setDetail(null);
    setDrawerOpen(true);
  }

  async function handleSave() {
    if (!formName.trim() || !formContent.trim()) return;
    setSaving(true);
    setMsg("");
    const tags = formTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    try {
      if (editing) {
        await api.patch(`/skills/${editing.id}`, {
          name: formName,
          description: formDesc || null,
          content: formContent,
          category: formCategory || null,
          tags,
        });
      } else {
        await api.post(`/skills`, {
          name: formName,
          description: formDesc || null,
          content: formContent,
          category: formCategory || null,
          tags,
          is_public: formPublic,
        });
      }
      setDrawerOpen(false);
      await loadSkills();
    } catch (e: unknown) {
      setMsg(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(s: Skill) {
    if (!confirm(t("confirmDelete", { name: s.name }))) return;
    await api.del(`/skills/${s.id}`);
    setDetail(null);
    await loadSkills();
  }

  async function handleUploadFiles(files: FileList) {
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        await api.upload<Skill>(`/skills/upload`, form);
      }
      await loadSkills();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("uploadFailed"));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  // 点卡片：列表返回的是摘要（无 content），拉取全量再展示，修复编辑拿到空内容的问题
  async function openDetail(s: Skill) {
    setDetail(s);
    try {
      const full = await api.get<Skill>(`/skills/${s.id}`);
      setDetail(full);
    } catch {
      /* 保持摘要 */
    }
  }

  async function downloadSkill(s: Skill, fmt: "zip" | "skill") {
    const token = getToken();
    const res = await fetch(`/api/skills/${s.id}/download?format=${fmt}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${s.name}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!ready) return null;

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <NavBar />

      <div className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        {/* Hero */}
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t("title")}</h1>
            <p className="mt-1 text-sm text-gray-500">{t("subtitle")}</p>
          </div>
          {canWrite && (
            <div className="flex gap-2">
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
              >
                {uploading ? t("uploading") : t("upload")}
              </button>
              <button
                onClick={openCreate}
                className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                {t("newSkill")}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".md,.zip,.skill"
                multiple
                className="hidden"
                onChange={(e) => e.target.files && handleUploadFiles(e.target.files)}
              />
            </div>
          )}
        </div>

        {/* 统计 */}
        <div className="mb-6 grid grid-cols-3 gap-4">
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <p className="text-xs text-gray-500">{t("statTotal")}</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{stats.total}</p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <p className="text-xs text-gray-500">{t("statCategory")}</p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{stats.catCount}</p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <p className="text-xs text-gray-500">{t("statLatest")}</p>
            <p className="mt-1 text-sm font-medium text-gray-700">
              {stats.latest ? stats.latest.slice(0, 10) : "—"}
            </p>
          </div>
        </div>

        {/* 搜索 + 分类筛选 */}
        <div className="mb-5">
          <div className="relative mb-3">
            <svg
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
                clipRule="evenodd"
              />
            </svg>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("searchPlaceholder")}
              className="w-full rounded-lg border border-gray-300 bg-white py-2.5 pl-10 pr-4 text-sm text-gray-900 placeholder-gray-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>
          {allCategories.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setCategory(null)}
                className={`rounded-full px-3 py-1 text-xs transition-colors ${
                  category === null
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-600 border border-gray-300 hover:bg-gray-50"
                }`}
              >
                {t("all")}
              </button>
              {allCategories.map((c) => (
                <button
                  key={c}
                  onClick={() => setCategory(c)}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${
                    category === c
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-600 border border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 卡片网格 */}
        {loading ? (
          <p className="mt-12 text-center text-gray-400">{t("loading")}</p>
        ) : skills.length === 0 ? (
          <div className="mt-12 text-center text-gray-400">
            <p>{t("notFound")}</p>
            <p className="mt-1 text-xs">{t("notFoundHint")}</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {skills.map((s) => (
              <button
                key={s.id}
                onClick={() => openDetail(s)}
                className="flex flex-col rounded-xl border border-gray-200 bg-white p-5 text-left transition-shadow hover:shadow-md"
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <span className="font-semibold text-gray-900">{s.name}</span>
                  {!s.is_public && (
                    <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
                      {t("private")}
                    </span>
                  )}
                </div>
                {s.description && (
                  <p className="mb-3 line-clamp-2 text-sm text-gray-500">{s.description}</p>
                )}
                <div className="mt-auto flex flex-wrap items-center gap-1.5">
                  {s.has_bundle && (
                    <span className="rounded bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-600">
                      📦 {t("hasBundle")}
                    </span>
                  )}
                  {s.category && (
                    <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600">
                      {s.category}
                    </span>
                  )}
                  {(s.tags ?? []).slice(0, 3).map((t) => (
                    <span
                      key={t}
                      className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500"
                    >
                      #{t}
                    </span>
                  ))}
                </div>
                <p className="mt-4 truncate text-xs text-gray-400">
                  {s.created_by_email ?? t("unknown")} · {s.updated_at.slice(0, 10)}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 详情弹窗 */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDetail(null)} />
          <div className="relative flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">{detail.name}</h2>
                {detail.description && (
                  <p className="mt-0.5 text-sm text-gray-500">{detail.description}</p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {detail.has_bundle && (
                    <span className="rounded bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-600">
                      📦 {t("hasBundle")}
                    </span>
                  )}
                  {detail.category && (
                    <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600">
                      {detail.category}
                    </span>
                  )}
                  {(detail.tags ?? []).map((t) => (
                    <span key={t} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                      #{t}
                    </span>
                  ))}
                </div>
              </div>
              <button
                onClick={() => setDetail(null)}
                className="text-gray-400 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-auto px-6 py-4">
              <pre className="whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm text-gray-800">
                {detail.content}
              </pre>
              <p className="mt-3 text-xs text-gray-400">
                {t("uploaderLabel")}：{detail.created_by_email ?? t("unknown")} · {t("updatedAt")}{" "}
                {detail.updated_at.slice(0, 10)}
              </p>
            </div>
            <div className="flex items-center justify-between gap-2 border-t border-gray-200 px-6 py-4">
              <div className="flex gap-2">
                <button
                  onClick={() => downloadSkill(detail, "zip")}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  {t("downloadZip")}
                </button>
                <button
                  onClick={() => downloadSkill(detail, "skill")}
                  className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  {t("downloadSkill")}
                </button>
              </div>
              {canWrite && (
                <div className="flex gap-2">
                  <button
                    onClick={() => handleDelete(detail)}
                    className="rounded-lg px-4 py-2 text-sm text-red-500 hover:bg-red-50"
                  >
                    {t("delete")}
                  </button>
                  <button
                    onClick={() => openEdit(detail)}
                    className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    {t("edit")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 创建/编辑抽屉 */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-black/40" onClick={() => setDrawerOpen(false)} />
          <div className="flex w-full max-w-lg flex-col bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
              <h2 className="font-semibold text-gray-900">
                {editing ? t("editTitle") : t("newTitle")}
              </h2>
              <button
                onClick={() => setDrawerOpen(false)}
                className="text-gray-400 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            <div className="flex flex-1 flex-col gap-4 overflow-auto px-6 py-4">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-gray-700">{t("fieldName")}</span>
                <input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-blue-500"
                  placeholder={t("namePlaceholder")}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-gray-700">{t("fieldDesc")}</span>
                <input
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  className="rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-blue-500"
                  placeholder={t("descPlaceholder")}
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-gray-700">{t("fieldCategory")}</span>
                  <input
                    value={formCategory}
                    onChange={(e) => setFormCategory(e.target.value)}
                    className="rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-blue-500"
                    placeholder={t("categoryPlaceholder")}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-gray-700">{t("fieldTags")}</span>
                  <input
                    value={formTags}
                    onChange={(e) => setFormTags(e.target.value)}
                    className="rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-blue-500"
                    placeholder={t("tagsPlaceholder")}
                  />
                </label>
              </div>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-gray-700">{t("fieldContent")}</span>
                <textarea
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  rows={12}
                  className="rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm text-gray-900 outline-none focus:border-blue-500"
                  placeholder={t("contentPlaceholder")}
                />
              </label>
              {!editing && (
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={formPublic}
                    onChange={(e) => setFormPublic(e.target.checked)}
                    className="h-4 w-4"
                  />
                  {t("makePublic")}
                </label>
              )}
              {msg && <p className="text-sm text-red-500">{msg}</p>}
            </div>
            <div className="flex justify-end gap-2 border-t border-gray-200 px-6 py-4">
              <button
                onClick={() => setDrawerOpen(false)}
                className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
              >
                {t("cancel")}
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !formName.trim() || !formContent.trim()}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
              >
                {saving ? t("saving") : t("save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
