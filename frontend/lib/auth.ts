// 统一的 token 存取（客户端）。所有对 token 的读写只经此模块。
"use client";

const TOKEN_KEY = "kb_token";
const EMAIL_KEY = "kb_email";

export function setAuth(token: string, _role: string, email?: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  // role 不再单独缓存——从 JWT payload 实时解析，避免升/降权后前端状态不同步
  if (email) localStorage.setItem(EMAIL_KEY, email);
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(EMAIL_KEY);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/** 从 JWT payload 解析 role，与服务端签发时保持一致。 */
export function getRole(): string | null {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role ?? null;
  } catch {
    return null;
  }
}

export function isAdmin(): boolean {
  return getRole() === "admin";
}

export function clearAuth(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
}

export function isLoggedIn(): boolean {
  return getToken() !== null;
}

// 登录后的落地页优先级（与 NavBar 菜单顺序一致）：模块 → 路由
const LANDING_ROUTES: { module: string; href: string }[] = [
  { module: "whatsnew", href: "/whatsnew" },
  { module: "chat", href: "/chat" },
  { module: "chatplus", href: "/chat-plus" },
  { module: "skills", href: "/skills" },
  { module: "documents", href: "/documents" },
  { module: "stats", href: "/stats" },
];

/**
 * 按用户权限选落地页：admin 恒定 /chat；普通用户取第一个有权限（≠none）的模块。
 * 都没有则退回 /account（人人可访问，避免落到 403 页）。
 * 动态 import api，避免 auth 与 api 的循环依赖。
 */
export async function resolveLandingPath(): Promise<string> {
  if (isAdmin()) return "/chat";
  try {
    const { api } = await import("./api");
    const perms = await api.get<Record<string, string>>("/auth/my-permissions");
    for (const { module, href } of LANDING_ROUTES) {
      if ((perms[module] ?? "none") !== "none") return href;
    }
  } catch {
    /* 权限拉取失败：退回账户页 */
  }
  return "/account";
}
