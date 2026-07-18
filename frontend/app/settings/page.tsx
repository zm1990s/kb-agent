"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import NavBar from "@/components/NavBar";
import SystemSettings from "@/components/admin/SystemSettings";
import { api } from "@/lib/api";
import { isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";

export default function SettingsPage() {
  const t = useTranslations("settings");
  const ready = useAuthGuard(["settings", "workspaces", "users"]);
  const router = useRouter();
  const [perms, setPerms] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    if (!ready) return;
    if (isAdmin()) {
      setPerms(null); // admin 跳过权限检查
      return;
    }
    api.get<Record<string, string>>("/auth/my-permissions")
      .then((p) => {
        const allowed = ["settings", "workspaces", "users"].some(
          (m) => (p[m] ?? "none") !== "none"
        );
        if (!allowed) {
          router.replace("/chat");
        } else {
          setPerms(p);
        }
      })
      .catch(() => router.replace("/chat"));
  }, [ready, router]);

  if (!ready) return null;
  if (!isAdmin() && perms === null) return null; // 等待权限加载

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto w-full max-w-5xl flex-1 p-4">
        <h1 className="mb-4 text-lg font-semibold">{t("title")}</h1>
        <SystemSettings perms={isAdmin() ? null : perms} />
      </main>
    </div>
  );
}
