"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useDialog } from "@/components/DialogProvider";
import { api, ApiError } from "@/lib/api";

interface UserRow {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
}
interface Group {
  id: string;
  name: string;
  description: string | null;
}
interface GroupRule {
  id: string;
  field: string;
  op: string;
  value: string;
}
interface GroupPerm {
  module: string;
  level: string;
}

const MODULE_KEYS = [
  "whatsnew",
  "chat",
  "chatplus",
  "skills",
  "documents",
  "workspaces",
  "users",
  "settings",
  "stats",
] as const;

export default function UserAdmin() {
  const t = useTranslations("admin");
  const [tab, setTab] = useState<"users" | "groups">("users");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setUsers(await api.get<UserRow[]>("/admin/users"));
      setGroups(await api.get<Group[]>("/admin/groups"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("user_load_failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="mb-4 flex gap-1 border-b">
        {(["users", "groups"] as const).map((tabKey) => (
          <button
            key={tabKey}
            onClick={() => setTab(tabKey)}
            className={`px-4 py-2 text-sm ${
              tab === tabKey
                ? "border-b-2 border-blue-600 font-medium text-blue-700"
                : "text-gray-500 hover:text-gray-800"
            }`}
          >
            {tabKey === "users" ? t("user_tab_users") : t("user_tab_groups")}
          </button>
        ))}
      </div>
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      {tab === "users" && (
        <UsersTab users={users} reload={load} setError={setError} />
      )}
      {tab === "groups" && (
        <GroupsTab groups={groups} reload={load} setError={setError} />
      )}
    </div>
  );
}

function UsersTab({
  users,
  reload,
  setError,
}: {
  users: UserRow[];
  reload: () => Promise<void>;
  setError: (s: string | null) => void;
}) {
  const t = useTranslations("admin");
  const { showConfirm, showPrompt } = useDialog();

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("user_op_failed"));
    }
  }

  return (
    <div className="overflow-hidden rounded border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left text-gray-500">
          <tr>
            <th className="px-4 py-2">{t("user_col_email")}</th>
            <th className="px-4 py-2">{t("user_col_role")}</th>
            <th className="px-4 py-2">{t("user_col_status")}</th>
            <th className="px-4 py-2">{t("user_col_actions")}</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t">
              <td className="px-4 py-2">{u.email}</td>
              <td className="px-4 py-2">
                <select
                  value={u.role}
                  onChange={(e) =>
                    act(() =>
                      api.patch(`/admin/users/${u.id}/role`, { role: e.target.value })
                    )
                  }
                  className="rounded border px-1 py-0.5 text-xs"
                >
                  <option value="admin">{t("user_role_admin")}</option>
                  <option value="user">{t("user_role_user")}</option>
                </select>
              </td>
              <td className="px-4 py-2">
                {!u.is_active ? (
                  <span className="text-gray-400">{t("user_inactive")}</span>
                ) : !u.email_verified ? (
                  <span className="text-yellow-600">{t("user_unverified")}</span>
                ) : (
                  <span className="text-green-700">{t("user_active")}</span>
                )}
              </td>
              <td className="whitespace-nowrap px-4 py-2">
                <button
                  onClick={() =>
                    act(() =>
                      api.patch(`/admin/users/${u.id}/active`, { is_active: !u.is_active })
                    )
                  }
                  className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700 hover:bg-gray-200"
                >
                  {u.is_active ? t("user_disable") : t("user_enable")}
                </button>
                {u.is_active && !u.email_verified && (
                  <button
                    onClick={() => act(() => api.patch(`/admin/users/${u.id}/verify-email`, {}))}
                    className="mr-1 rounded bg-yellow-50 px-2 py-1 text-xs text-yellow-700 hover:bg-yellow-100"
                  >
                    {t("user_mark_verified")}
                  </button>
                )}
                <button
                  onClick={async () => {
                    const pw = await showPrompt(t("user_reset_password_prompt"));
                    if (pw)
                      act(() =>
                        api.post(`/admin/users/${u.id}/reset-password`, { new_password: pw })
                      );
                  }}
                  className="rounded bg-gray-100 px-2 py-1 text-xs text-blue-700 hover:bg-gray-200"
                >
                  {t("user_reset_password")}
                </button>
                <button
                  onClick={async () => {
                    if (await showConfirm(t("user_delete_confirm", { email: u.email })))
                      act(() => api.del(`/admin/users/${u.id}`));
                  }}
                  className="ml-1 rounded bg-gray-100 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                >
                  {t("user_delete")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GroupsTab({
  groups,
  reload,
  setError,
}: {
  groups: Group[];
  reload: () => Promise<void>;
  setError: (s: string | null) => void;
}) {
  const t = useTranslations("admin");
  const { showConfirm, showPrompt } = useDialog();
  const [selected, setSelected] = useState<string | null>(null);
  const [rules, setRules] = useState<GroupRule[]>([]);
  const [perms, setPerms] = useState<GroupPerm[]>([]);

  const loadDetail = useCallback(async (gid: string) => {
    try {
      setRules(await api.get<GroupRule[]>(`/admin/groups/${gid}/rules`));
      setPerms(await api.get<GroupPerm[]>(`/admin/groups/${gid}/permissions`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("user_load_failed"));
    }
  }, [setError, t]);

  useEffect(() => {
    if (selected) loadDetail(selected);
  }, [selected, loadDetail]);

  async function act(fn: () => Promise<unknown>, reloadDetail = true) {
    setError(null);
    try {
      await fn();
      await reload();
      if (selected && reloadDetail) await loadDetail(selected);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("user_op_failed"));
    }
  }

  const permLevel = (m: string) =>
    perms.find((p) => p.module === m)?.level ?? "none";

  return (
    <div className="flex gap-6">
      <aside className="w-52 shrink-0 flex flex-col gap-1">
        <p className="px-1 pb-1 text-xs font-medium text-gray-500 uppercase tracking-wide">
          {t("group_list_title")}
        </p>
        <ul className="space-y-0.5">
          {groups.map((g) => (
            <li key={g.id} className="group flex items-center">
              <button
                onClick={() => setSelected(g.id)}
                className={`flex-1 truncate rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  selected === g.id
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-700 hover:bg-gray-100"
                }`}
              >
                {g.name}
              </button>
              <button
                onClick={async () => {
                  if (await showConfirm(t("group_delete_confirm", { name: g.name }))) {
                    act(() => api.del(`/admin/groups/${g.id}`), false);
                    if (selected === g.id) setSelected(null);
                  }
                }}
                className="hidden px-1 text-xs text-red-400 hover:text-red-600 group-hover:block"
              >
                ✕
              </button>
            </li>
          ))}
          {groups.length === 0 && (
            <li className="px-3 py-2 text-xs text-gray-400">{t("group_no_groups")}</li>
          )}
        </ul>
        <button
          onClick={async () => {
            const name = await showPrompt(t("group_new_prompt"));
            if (name) act(() => api.post("/admin/groups", { name }), false);
          }}
          className="mt-2 flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-3 py-2 text-sm text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
        >
          <span className="text-base leading-none">+</span>
          {t("group_new")}
        </button>
      </aside>

      <div className="flex-1 min-w-0 space-y-4">
        {!selected && (
          <p className="text-sm text-gray-400">{t("group_select_hint")}</p>
        )}
        {selected && (
          <>
            <section className="rounded border bg-white p-4">
              <h3 className="mb-2 text-sm font-medium">{t("group_rules_title")}</h3>
              <p className="mb-2 text-xs text-gray-400">
                {t("group_rules_desc")}
              </p>
              <ul className="mb-3 space-y-1 text-sm">
                {rules.map((r) => (
                  <li
                    key={r.id}
                    className="flex items-center justify-between rounded bg-gray-50 px-3 py-1.5"
                  >
                    <span className="text-gray-700">
                      {r.field} {r.op} <code className="text-blue-700">{r.value}</code>
                    </span>
                    <button
                      onClick={() => act(() => api.del(`/admin/rules/${r.id}`))}
                      className="text-xs text-red-500 hover:underline"
                    >
                      {t("group_delete_rule")}
                    </button>
                  </li>
                ))}
                {rules.length === 0 && <li className="text-gray-400">{t("group_no_rules")}</li>}
              </ul>
              <RuleForm
                onAdd={(field, op, value) =>
                  act(() =>
                    api.post(`/admin/groups/${selected}/rules`, { field, op, value })
                  )
                }
              />
            </section>

            <section className="rounded border bg-white p-4">
              <h3 className="mb-2 text-sm font-medium">{t("group_perms_title")}</h3>
              <div className="space-y-2">
                {MODULE_KEYS.map((key) => (
                  <div key={key} className="flex items-center gap-3 text-sm">
                    <span className="w-24 text-gray-600">{t(`module_${key}`)}</span>
                    {(["none", "read", "write"] as const).map((lv) => (
                      <label key={lv} className="flex items-center gap-1 text-xs">
                        <input
                          type="radio"
                          name={`perm-${key}`}
                          checked={permLevel(key) === lv}
                          onChange={() =>
                            act(() =>
                              api.put(`/admin/groups/${selected}/permissions`, {
                                module: key,
                                level: lv,
                              })
                            )
                          }
                        />
                        {lv === "none" ? t("group_perm_none") : lv === "read" ? t("group_perm_read") : t("group_perm_write")}
                      </label>
                    ))}
                  </div>
                ))}
              </div>
              <button
                onClick={() => act(() => api.post("/admin/recompute-memberships"), false)}
                className="mt-4 rounded border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100"
              >
                {t("group_recompute")}
              </button>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function RuleForm({ onAdd }: { onAdd: (field: string, op: string, value: string) => void }) {
  const t = useTranslations("admin");
  const [field, setField] = useState("email_domain");
  const [op, setOp] = useState("equals");
  const [value, setValue] = useState("");

  function splitValues(raw: string): string[] {
    return raw.split(/[\s,;，；\n]+/).map((v) => v.trim()).filter(Boolean);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const parts = splitValues(value);
    if (parts.length === 0) return;
    parts.forEach((v) => onAdd(field, op, v));
    setValue("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === "," || e.key === " ") {
      const parts = splitValues(value);
      if (parts.length > 0) {
        e.preventDefault();
        parts.forEach((v) => onAdd(field, op, v));
        setValue("");
      }
    }
  }

  const preview = splitValues(value);

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <select
          value={field}
          onChange={(e) => setField(e.target.value)}
          className="rounded border px-2 py-1 text-xs"
        >
          <option value="email_domain">{t("group_rule_field_domain")}</option>
          <option value="email">{t("group_rule_field_email")}</option>
          <option value="role">{t("group_rule_field_role")}</option>
        </select>
        <select
          value={op}
          onChange={(e) => setOp(e.target.value)}
          className="rounded border px-2 py-1 text-xs"
        >
          <option value="equals">{t("group_rule_op_equals")}</option>
          <option value="endswith">{t("group_rule_op_endswith")}</option>
          <option value="contains">{t("group_rule_op_contains")}</option>
        </select>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("group_rule_value_placeholder")}
          className="flex-1 rounded border px-2 py-1 text-xs"
        />
        <button className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">
          {t("group_rule_add")}
        </button>
      </div>
      {preview.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {preview.map((v) => (
            <span key={v} className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
              {v}
            </span>
          ))}
          <span className="text-xs text-gray-400">{t("group_rule_will_add", { count: preview.length })}</span>
        </div>
      )}
    </form>
  );
}
