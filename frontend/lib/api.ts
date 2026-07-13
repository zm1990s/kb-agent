// 统一 API 客户端。所有后端调用走相对 /api/*（单端口反代），
// 自动注入 Authorization，401 时清除凭据并跳登录。
"use client";

import { clearAuth, getToken } from "./auth";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  // 上传用：直接传 FormData（不设 JSON 头）
  form?: FormData;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const res = await fetch(`/api${path}`, {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
  });

  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "未认证");
  }

  if (!res.ok) {
    let detail = `请求失败 (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) detail = typeof data.detail === "string" ? data.detail : detail;
    } catch {
      // 忽略非 JSON 响应
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined as T;
  return (await res.json()) as T;
}

// SSE 流式请求：逐个回调 (event, data)。用 fetch+ReadableStream，
// 因为 EventSource 不支持 POST / 自定义 Authorization 头。
// signal 可传入 AbortController.signal 以中途取消。
export async function stream(
  path: string,
  body: unknown,
  onEvent: (event: string, data: unknown) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "未认证");
  }
  if (!res.ok || !res.body) throw new ApiError(res.status, `流式请求失败 (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE 事件以空行分隔
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        let event = "message";
        let data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (data) {
          try {
            onEvent(event, JSON.parse(data));
          } catch {
            /* 忽略非 JSON 数据行 */
          }
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    throw err;
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", form }),
  stream,
};
