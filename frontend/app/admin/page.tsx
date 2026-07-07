"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import NavBar from "@/components/NavBar";
import SystemSettings from "@/components/admin/SystemSettings";
import WorkspaceAdmin from "@/components/admin/WorkspaceAdmin";
import { isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";

type Tab = "workspace" | "system";

const TABS: { id: Tab; label: string }[] = [
  { id: "workspace", label: "空间管理" },
  { id: "system", label: "系统设置" },
];

export default function AdminPage() {
  const ready = useAuthGuard();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("workspace");

  if (!ready) return null;
  if (!isAdmin()) {
    router.replace("/chat");
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto w-full max-w-3xl flex-1 p-4">
        <h1 className="mb-4 text-lg font-semibold">管理后台</h1>

        <div className="mb-4 flex gap-1 border-b">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm ${
                tab === t.id
                  ? "border-b-2 border-blue-600 font-medium text-blue-700"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "workspace" ? <WorkspaceAdmin /> : <SystemSettings />}
      </main>
    </div>
  );
}
