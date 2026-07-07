// 首页占位；MF-U3+ 会替换为登录/主界面路由。
export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">KB-Agent</h1>
      <p className="text-gray-600">共享 Agent 知识平台 · 前端已就绪</p>
    </main>
  );
}
