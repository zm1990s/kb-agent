"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";

interface Props {
  conversationId: string | null;
  filename: string;
  canWrite?: boolean;
}

// 标准入口名：单文件必须是 SKILL.md；压缩包为 .zip / .skill（包内含 SKILL.md）
function isEligibleSkillFile(name: string): boolean {
  const lower = name.toLowerCase();
  return lower === "skill.md" || lower.endsWith(".zip") || lower.endsWith(".skill");
}

function stripExt(name: string): string {
  const i = name.lastIndexOf(".");
  return i > 0 ? name.slice(0, i) : name;
}

interface FilePreview {
  name: string | null;
  description: string | null;
  category: string | null;
  tags: string[];
}

export default function SaveAsSkillButton({ conversationId, filename, canWrite = true }: Props) {
  const t = useTranslations("chatComponents");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState("");
  const [isPublic, setIsPublic] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (!isEligibleSkillFile(filename) || !canWrite) return null;

  async function openDialog() {
    // 先用文件名兜底，随后拉取 frontmatter 预览覆盖
    setName(stripExt(filename));
    setDescription("");
    setCategory("");
    setTags("");
    setIsPublic(true);
    setMsg(null);
    setDone(false);
    setOpen(true);
    if (!conversationId) return;
    setLoadingPreview(true);
    try {
      const params = new URLSearchParams({
        conversation_id: conversationId,
        filename,
      });
      const p = await api.get<FilePreview>(
        `/skills/conversation-file-preview?${params.toString()}`
      );
      // 解析到才覆盖；解析不到的字段留空让用户填写
      if (p.name) setName(p.name);
      if (p.description) setDescription(p.description);
      if (p.category) setCategory(p.category);
      if (p.tags && p.tags.length > 0) setTags(p.tags.join(", "));
    } catch {
      /* 预览失败静默：保留文件名兜底，用户可手填 */
    } finally {
      setLoadingPreview(false);
    }
  }

  async function submit() {
    if (!conversationId) return;
    setSaving(true);
    setMsg(null);
    try {
      await api.post("/skills/from-conversation-file", {
        conversation_id: conversationId,
        filename,
        name: name.trim() || null,
        description: description.trim() || null,
        category: category.trim() || null,
        tags: tags.trim()
          ? tags.split(",").map((t) => t.trim()).filter(Boolean)
          : null,
        is_public: isPublic,
      });
      setDone(true);
      setTimeout(() => setOpen(false), 900);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={openDialog}
        className="flex items-center gap-1 rounded-lg border border-purple-200 bg-purple-50 px-2 py-1.5 text-xs text-purple-700 hover:bg-purple-100 transition-colors"
        title={t("saveAsSkill")}
      >
        <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="currentColor">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.286 3.966a1 1 0 00.95.69h4.17c.969 0 1.371 1.24.588 1.81l-3.375 2.452a1 1 0 00-.363 1.118l1.287 3.966c.3.922-.755 1.688-1.54 1.118l-3.375-2.452a1 1 0 00-1.175 0l-3.375 2.452c-.784.57-1.838-.196-1.539-1.118l1.287-3.966a1 1 0 00-.363-1.118L2.03 9.393c-.783-.57-.38-1.81.588-1.81h4.17a1 1 0 00.95-.69l1.286-3.966z" />
        </svg>
        {t("saveAsSkill")}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h2 className="mb-1 text-lg font-semibold text-gray-900">{t("saveAsSkill")}</h2>
            <p className="mb-4 text-xs text-gray-500">
              {t("saveAsSkillSourceLabel")}<span className="font-mono">{filename}</span>
              。{loadingPreview ? t("saving") : t("saveAsSkillHint")}
            </p>

            {done ? (
              <p className="py-6 text-center text-sm text-green-600">{t("savedToHub")}</p>
            ) : (
              <>
                <label className="mb-3 block text-sm">
                  <span className="mb-1 block text-gray-700">{t("name")}</span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-purple-500"
                    placeholder={t("namePlaceholder")}
                  />
                </label>
                <label className="mb-3 block text-sm">
                  <span className="mb-1 block text-gray-700">{t("desc")}</span>
                  <input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-purple-500"
                    placeholder={t("descAutoHint")}
                  />
                </label>
                <label className="mb-3 block text-sm">
                  <span className="mb-1 block text-gray-700">{t("category")}</span>
                  <input
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-purple-500"
                    placeholder={t("categoryPlaceholder")}
                  />
                </label>
                <label className="mb-3 block text-sm">
                  <span className="mb-1 block text-gray-700">{t("tags")}</span>
                  <input
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-purple-500"
                    placeholder={t("tagsPlaceholder")}
                  />
                </label>
                <label className="mb-4 flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={isPublic}
                    onChange={(e) => setIsPublic(e.target.checked)}
                    className="h-4 w-4"
                  />
                  {t("makePublic")}
                </label>

                {msg && <p className="mb-3 text-sm text-red-500">{msg}</p>}

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="rounded-lg px-4 py-2 text-sm text-gray-500 hover:text-gray-700"
                  >
                    {t("cancel")}
                  </button>
                  <button
                    type="button"
                    onClick={submit}
                    disabled={saving}
                    className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-40"
                  >
                    {saving ? t("saving") : t("confirmSave")}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
