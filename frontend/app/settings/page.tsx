"use client";

import { useRouter } from "next/navigation";
import NavBar from "@/components/NavBar";
import SystemSettings from "@/components/admin/SystemSettings";
import { isAdmin } from "@/lib/auth";
import { useAuthGuard } from "@/lib/useAuthGuard";

export default function SettingsPage() {
  const ready = useAuthGuard();
  const router = useRouter();

  if (!ready) return null;
  if (!isAdmin()) {
    router.replace("/chat");
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto w-full max-w-3xl flex-1 p-4">
        <h1 className="mb-4 text-lg font-semibold">系统设置</h1>
        <SystemSettings />
      </main>
    </div>
  );
}
