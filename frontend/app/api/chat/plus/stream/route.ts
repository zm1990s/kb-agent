// 直接透传后端 SSE 流，绕过 Next.js rewrites 对流式响应的缓冲。
import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL || "http://backend:8000";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const authHeader = req.headers.get("authorization") ?? "";

  const upstream = await fetch(`${BACKEND}/chat/plus/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authHeader ? { Authorization: authHeader } : {}),
    },
    body,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
