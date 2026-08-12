"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";

interface SsoClient {
  id: string;
  uri_prefix: string;
  description: string | null;
  created_at: string;
}

export default function SSOSettings() {
  const t = useTranslations("settings");

  const [enabled, setEnabled] = useState(false);
  const [clients, setClients] = useState<SsoClient[]>([]);
  const [newUri, setNewUri] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [settings, list] = await Promise.all([
        api.get<{ enabled: boolean }>("/admin/sso-settings"),
        api.get<SsoClient[]>("/admin/sso-clients"),
      ]);
      setEnabled(settings.enabled);
      setClients(list);
    } catch {
      // 静默失败
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function toggleEnabled() {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      const res = await api.put<{ enabled: boolean }>("/admin/sso-settings", { enabled: !enabled });
      setEnabled(res.enabled);
      setMsg(t("sso_saved"));
      setTimeout(() => setMsg(null), 2000);
    } catch {
      setError(t("sso_save_error"));
    } finally {
      setBusy(false);
    }
  }

  async function addClient() {
    const uri = newUri.trim();
    if (!uri) return;
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      const c = await api.post<SsoClient>("/admin/sso-clients", {
        uri_prefix: uri,
        description: newDesc.trim(),
      });
      setClients((prev) => [...prev, c]);
      setNewUri("");
      setNewDesc("");
      setAddOpen(false);
      setMsg(t("sso_client_added"));
      setTimeout(() => setMsg(null), 2000);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(t("sso_client_duplicate"));
      } else {
        setError(t("sso_client_add_error"));
      }
    } finally {
      setBusy(false);
    }
  }

  async function removeClient(id: string) {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      await api.del(`/admin/sso-clients/${id}`);
      setClients((prev) => prev.filter((c) => c.id !== id));
    } catch {
      setError(t("sso_client_remove_error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded border bg-white p-4">
      <h2 className="mb-1 text-sm font-medium">{t("sso_title")}</h2>
      <p className="mb-4 text-xs text-gray-400">{t("sso_desc")}</p>

      {/* 功能开关 */}
      <div className="mb-5 flex items-center gap-3">
        <button
          type="button"
          onClick={toggleEnabled}
          disabled={busy}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
            enabled ? "bg-blue-600" : "bg-gray-200"
          }`}
          role="switch"
          aria-checked={enabled}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              enabled ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
        <span className="text-sm text-gray-700">
          {enabled ? t("sso_enabled_label") : t("sso_disabled_label")}
        </span>
      </div>

      {/* 允许的回调 URI 列表 */}
      <fieldset disabled={!enabled} className={!enabled ? "opacity-50 pointer-events-none" : ""}>
        <p className="mb-2 text-xs font-medium text-gray-600">{t("sso_clients_title")}</p>

        {clients.length === 0 && (
          <p className="mb-2 text-xs text-gray-400">{t("sso_clients_empty")}</p>
        )}

        <div className="space-y-1.5 mb-3">
          {clients.map((c) => (
            <div key={c.id} className="flex items-start gap-2 rounded border bg-gray-50 px-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-mono text-gray-800 truncate">{c.uri_prefix}</p>
                {c.description && (
                  <p className="text-xs text-gray-500 mt-0.5">{c.description}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => removeClient(c.id)}
                disabled={busy}
                className="shrink-0 rounded px-2 py-1 text-xs text-gray-400 hover:bg-red-50 hover:text-red-500"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {addOpen ? (
          <div className="space-y-2 rounded border p-3">
            <input
              className="w-full rounded border px-2 py-1 text-xs font-mono"
              placeholder="https://app.example.com"
              value={newUri}
              onChange={(e) => setNewUri(e.target.value)}
            />
            <input
              className="w-full rounded border px-2 py-1 text-xs"
              placeholder={t("sso_client_desc_placeholder")}
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={addClient}
                disabled={busy || !newUri.trim()}
                className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {t("sso_client_confirm_add")}
              </button>
              <button
                type="button"
                onClick={() => { setAddOpen(false); setNewUri(""); setNewDesc(""); }}
                className="rounded border px-3 py-1 text-xs text-gray-500 hover:bg-gray-50"
              >
                {t("cancel")}
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setAddOpen(true)}
            className="rounded border px-2 py-1 text-xs text-gray-500 hover:bg-gray-50"
          >
            + {t("sso_client_add")}
          </button>
        )}
      </fieldset>

      {msg && <p className="mt-3 text-xs text-green-600">{msg}</p>}
      {error && <p className="mt-3 text-xs text-red-500">{error}</p>}
    </section>
  );
}
