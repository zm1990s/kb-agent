// 路由守卫 hook：未登录跳 /login；可选校验模块权限，不足则跳落地页。
// 后端仍是唯一防线（每个端点强制鉴权），此处仅避免用户落到 403 页面。
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";
import { isAdmin, isLoggedIn, resolveLandingPath } from "./auth";

/**
 * @param module 需要的模块权限（≠none 即可）。可传单个或多个——多个时满足其一即放行
 *   （如 settings 页需 settings/workspaces/users 任一）。省略则只校验登录。
 */
export function useAuthGuard(module?: string | string[]): boolean {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  // 内联数组每次渲染都是新引用；用稳定 key 作 effect 依赖，避免反复触发
  const moduleKey = Array.isArray(module) ? module.join(",") : (module ?? "");

  useEffect(() => {
    let cancelled = false;
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    // 无需模块校验，或 admin 恒放行
    if (!module || isAdmin()) {
      setReady(true);
      return;
    }
    const needed = moduleKey.split(",").filter(Boolean);
    api
      .get<Record<string, string>>("/auth/my-permissions")
      .then(async (perms) => {
        if (cancelled) return;
        const allowed = needed.some((m) => (perms[m] ?? "none") !== "none");
        if (allowed) {
          setReady(true);
        } else {
          // 无权限：重定向到用户实际可访问的落地页（不渲染出 403）
          router.replace(await resolveLandingPath());
        }
      })
      .catch(() => {
        // 权限拉取失败：保守放行，交由后端端点鉴权兜底
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [router, moduleKey]);

  return ready;
}
