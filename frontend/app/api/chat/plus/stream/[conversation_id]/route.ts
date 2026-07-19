// 重连 SSE 流：直接透传后端流，绕过 Next.js rewrites 的缓冲。
import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL || "http://backend:8000";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ conversation_id: string }> },
) {
  const { conversation_id } = await params;
  const authHeader = req.headers.get("authorization") ?? "";

  const upstream = await fetch(
    `${BACKEND}/chat/plus/stream/${encodeURIComponent(conversation_id)}`,
    {
      method: "GET",
      headers: {
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
    },
  );

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
