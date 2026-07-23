"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";

interface Skill {
  id: string;
  name: string;
  description: string | null;
  is_public: boolean;
}

interface Props {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}

export default function SkillPicker({ selectedIds, onChange }: Props) {
  const t = useTranslations("chatComponents");
  const [open, setOpen] = useState(false);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<Skill[]>(`/skills`).then(setSkills).catch(() => setSkills([]));
  }, []);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function toggle(id: string) {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((s) => s !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  }

  const selectedNames = skills.filter((s) => selectedIds.includes(s.id)).map((s) => s.name);
  const filtered = search.trim()
    ? skills.filter((s) => s.name.toLowerCase().includes(search.toLowerCase()) || s.description?.toLowerCase().includes(search.toLowerCase()))
    : skills;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-xs text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors"
        title={t("selectSkill")}
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
        {selectedNames.length === 0 ? t("selectSkill") : selectedNames.join("、").slice(0, 20)}
        {selectedNames.length > 0 && (
          <span className="ml-0.5 rounded-full bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-600">
            {selectedNames.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-1 w-64 rounded-lg border border-gray-200 bg-white py-1 shadow-xl">
          <div className="px-2 py-1.5 border-b border-gray-100">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索 Skill…"
              className="w-full rounded-md border border-gray-200 px-2 py-1 text-xs outline-none focus:border-blue-400"
            />
          </div>
          {skills.length === 0 ? (
            <p className="px-4 py-3 text-xs text-gray-400">{t("noSkill")}</p>
          ) : (
            <div className="max-h-64 overflow-y-auto">
              {filtered.length === 0 ? (
                <p className="px-4 py-3 text-xs text-gray-400">无匹配结果</p>
              ) : filtered.map((s) => (
                <label
                  key={s.id}
                  className="flex cursor-pointer items-start gap-2 px-3 py-2 hover:bg-gray-50"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(s.id)}
                    onChange={() => toggle(s.id)}
                    className="mt-0.5 h-3.5 w-3.5 shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-gray-800">{s.name}</p>
                    {s.description && (
                      <p className="truncate text-xs text-gray-400">{s.description}</p>
                    )}
                  </div>
                </label>
              ))}
            </div>
          )}
          {selectedIds.length > 0 && (
            <div className="border-t border-gray-100 px-3 py-1.5">
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-xs text-red-400 hover:text-red-600"
              >
                {t("clearAll")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
