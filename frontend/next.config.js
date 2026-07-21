/** @type {import('next').NextConfig} */
// 单端口入口：前端所有 /api/* 请求经 rewrites 反代到后端 FastAPI。
// 后端地址仅通过环境变量注入（compose 网络内的服务名），前端代码不硬编码。
const BACKEND_URL = process.env.BACKEND_URL || "http://backend:8000";

const nextConfig = {
  // 关闭 Next 内置 gzip：它会压缩经 rewrites 反代的 SSE 响应，而 gzip 攒够压缩块
  // 才输出，导致聊天+ 重连流事件被缓冲、直到生成结束才一次性解出（切走返回后
  // thinking 不再实时更新）。生产环境前置 nginx/CDN 负责静态资源压缩，此处关闭安全。
  compress: false,

  experimental: {
    // 上传文件经 /api/* 反代到后端，默认 10MB 限制会截断大文件（ECONNRESET）
    proxyClientMaxBodySize: "200mb",
    proxyTimeout: 120000,
  },

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },

  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
