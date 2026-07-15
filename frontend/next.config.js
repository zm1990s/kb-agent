/** @type {import('next').NextConfig} */
// 单端口入口：前端所有 /api/* 请求经 rewrites 反代到后端 FastAPI。
// 后端地址仅通过环境变量注入（compose 网络内的服务名），前端代码不硬编码。
const BACKEND_URL = process.env.BACKEND_URL || "http://backend:8000";

const nextConfig = {
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
