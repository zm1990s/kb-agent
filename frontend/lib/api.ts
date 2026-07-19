// 统一 API 客户端。所有后端调用走相对 /api/*（单端口反代），
// 自动注入 Authorization，401 时先静默 refresh，失败才清除凭据并跳登录。
"use client";

import { clearAuth, getToken, setAuth } from "./auth";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  // 上传用：直接传 FormData（不设 JSON 头）
  form?: FormData;
}

// 防止并发多个 401 同时触发多次 refresh
let _refreshing: Promise<boolean> | null = null;

async function _tryRefresh(): Promise<boolean> {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    try {
      const res = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
      if (!res.ok) return false;
      const data = await res.json() as { access_token: string; role: string };
      setAuth(data.access_token, data.role);
      return true;
    } catch {
      return false;
    } finally {
      _refreshing = null;
    }
  })();
  return _refreshing;
}

function _redirectToLogin() {
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

async function request<T>(path: string, opts: RequestOptions = {}, _retry = true): Promise<T> {
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
    if (_retry && await _tryRefresh()) {
      return request<T>(path, opts, false);
    }
    clearAuth();
    _redirectToLogin();
    throw new ApiError(401, "未认证");
  }

  if (!res.ok) {
    let message = `请求失败 (${res.status})`;
    let rawDetail: unknown = null;
    try {
      const data = await res.json();
      rawDetail = data?.detail ?? null;
      if (typeof rawDetail === "string") message = rawDetail;
    } catch {
      // 忽略非 JSON 响应
    }
    throw new ApiError(res.status, message, rawDetail);
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
  _retry = true,
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
    if (_retry && await _tryRefresh()) {
      return stream(path, body, onEvent, signal, false);
    }
    clearAuth();
    _redirectToLogin();
    throw new ApiError(401, "未认证");
  }
  return consumeStream(res, onEvent);
}

// GET 版 SSE：重连正在后台运行的生成流（无 body）。
export async function streamGet(
  path: string,
  onEvent: (event: string, data: unknown) => void,
  signal?: AbortSignal,
  _retry = true,
): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, { method: "GET", headers, signal });

  if (res.status === 401) {
    if (_retry && await _tryRefresh()) {
      return streamGet(path, onEvent, signal, false);
    }
    clearAuth();
    _redirectToLogin();
    throw new ApiError(401, "未认证");
  }
  return consumeStream(res, onEvent);
}

async function consumeStream(
  res: Response,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
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
  streamGet,
};
