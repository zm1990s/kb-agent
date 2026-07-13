"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

interface UserRow {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
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

const MODULES = [
  { key: "whatsnew", label: "新动态" },
  { key: "chat", label: "对话查询" },
  { key: "documents", label: "文档管理" },
  { key: "workspaces", label: "空间管理" },
  { key: "users", label: "用户管理" },
  { key: "settings", label: "系统设置" },
  { key: "stats", label: "数据统计" },
];

export default function UserAdmin() {
  const [tab, setTab] = useState<"users" | "groups">("users");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setUsers(await api.get<UserRow[]>("/admin/users"));
      setGroups(await api.get<Group[]>("/admin/groups"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="mb-4 flex gap-1 border-b">
        {(["users", "groups"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm ${
              tab === t
                ? "border-b-2 border-blue-600 font-medium text-blue-700"
                : "text-gray-500 hover:text-gray-800"
            }`}
          >
            {t === "users" ? "用户" : "用户组与权限"}
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
  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "操作失败");
    }
  }

  return (
    <div className="overflow-hidden rounded border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-left text-gray-500">
          <tr>
            <th className="px-4 py-2">邮箱</th>
            <th className="px-4 py-2">角色</th>
            <th className="px-4 py-2">状态</th>
            <th className="px-4 py-2">操作</th>
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
                  <option value="admin">管理员</option>
                  <option value="user">普通用户</option>
                </select>
              </td>
              <td className="px-4 py-2">
                <span className={u.is_active ? "text-green-700" : "text-gray-400"}>
                  {u.is_active ? "启用" : "禁用"}
                </span>
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
                  {u.is_active ? "禁用" : "启用"}
                </button>
                <button
                  onClick={() => {
                    const pw = window.prompt("为该用户设置新密码（≥8 位）");
                    if (pw)
                      act(() =>
                        api.post(`/admin/users/${u.id}/reset-password`, { new_password: pw })
                      );
                  }}
                  className="rounded bg-gray-100 px-2 py-1 text-xs text-blue-700 hover:bg-gray-200"
                >
                  重置密码
                </button>
                <button
                  onClick={() => {
                    if (window.confirm(`确认永久删除用户「${u.email}」？此操作不可恢复。`))
                      act(() => api.del(`/admin/users/${u.id}`));
                  }}
                  className="ml-1 rounded bg-gray-100 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                >
                  删除
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
  const [selected, setSelected] = useState<string | null>(null);
  const [rules, setRules] = useState<GroupRule[]>([]);
  const [perms, setPerms] = useState<GroupPerm[]>([]);

  const loadDetail = useCallback(async (gid: string) => {
    try {
      setRules(await api.get<GroupRule[]>(`/admin/groups/${gid}/rules`));
      setPerms(await api.get<GroupPerm[]>(`/admin/groups/${gid}/permissions`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载组详情失败");
    }
  }, [setError]);

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
      setError(err instanceof ApiError ? err.message : "操作失败");
    }
  }

  const permLevel = (m: string) =>
    perms.find((p) => p.module === m)?.level ?? "none";

  return (
    <div className="flex gap-4">
      <div className="w-56 shrink-0 rounded border bg-white">
        <button
          onClick={() => {
            const name = window.prompt("新用户组名称");
            if (name) act(() => api.post("/admin/groups", { name }), false);
          }}
          className="m-2 rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
        >
          + 新建组
        </button>
        {groups.map((g) => (
          <div
            key={g.id}
            className={`group flex items-center ${
              selected === g.id ? "bg-blue-50" : "hover:bg-gray-100"
            }`}
          >
            <button
              onClick={() => setSelected(g.id)}
              className={`flex-1 truncate px-3 py-2 text-left text-sm ${
                selected === g.id ? "text-blue-700" : "text-gray-600"
              }`}
            >
              {g.name}
            </button>
            <button
              onClick={() => {
                if (window.confirm(`删除组「${g.name}」？`)) {
                  act(() => api.del(`/admin/groups/${g.id}`), false);
                  if (selected === g.id) setSelected(null);
                }
              }}
              className="hidden px-2 text-xs text-red-500 group-hover:block"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="flex-1 space-y-4">
        {!selected && (
          <p className="text-sm text-gray-400">选择一个组以配置入组规则与模块权限。</p>
        )}
        {selected && (
          <>
            <section className="rounded border bg-white p-4">
              <h3 className="mb-2 text-sm font-medium">自动入组规则</h3>
              <p className="mb-2 text-xs text-gray-400">
                {'任一规则命中即入组。改规则后可点击"重算全部用户入组"刷新。'}
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
                      删除
                    </button>
                  </li>
                ))}
                {rules.length === 0 && <li className="text-gray-400">暂无规则</li>}
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
              <h3 className="mb-2 text-sm font-medium">模块权限（RBAC）</h3>
              <div className="space-y-2">
                {MODULES.map((m) => (
                  <div key={m.key} className="flex items-center gap-3 text-sm">
                    <span className="w-24 text-gray-600">{m.label}</span>
                    {(["none", "read", "write"] as const).map((lv) => (
                      <label key={lv} className="flex items-center gap-1 text-xs">
                        <input
                          type="radio"
                          name={`perm-${m.key}`}
                          checked={permLevel(m.key) === lv}
                          onChange={() =>
                            act(() =>
                              api.put(`/admin/groups/${selected}/permissions`, {
                                module: m.key,
                                level: lv,
                              })
                            )
                          }
                        />
                        {lv === "none" ? "无" : lv === "read" ? "只读" : "读写"}
                      </label>
                    ))}
                  </div>
                ))}
              </div>
              <button
                onClick={() => act(() => api.post("/admin/recompute-memberships"), false)}
                className="mt-4 rounded border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100"
              >
                重算全部用户入组
              </button>
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function RuleForm({ onAdd }: { onAdd: (field: string, op: string, value: string) => void }) {
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
          <option value="email_domain">邮箱域名</option>
          <option value="email">邮箱</option>
          <option value="role">角色</option>
        </select>
        <select
          value={op}
          onChange={(e) => setOp(e.target.value)}
          className="rounded border px-2 py-1 text-xs"
        >
          <option value="equals">等于</option>
          <option value="endswith">以…结尾</option>
          <option value="contains">包含</option>
        </select>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="支持空格/逗号/回车分隔多个值"
          className="flex-1 rounded border px-2 py-1 text-xs"
        />
        <button className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">
          添加规则
        </button>
      </div>
      {preview.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {preview.map((v) => (
            <span key={v} className="rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
              {v}
            </span>
          ))}
          <span className="text-xs text-gray-400">将添加 {preview.length} 条规则</span>
        </div>
      )}
    </form>
  );
}
