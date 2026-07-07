/** @type {import('next').NextConfig} */
// 单端口入口：前端所有 /api/* 请求经 rewrites 反代到后端 FastAPI。
// 后端地址仅通过环境变量注入（compose 网络内的服务名），前端代码不硬编码。
const BACKEND_URL = process.env.BACKEND_URL || "http://backend:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
