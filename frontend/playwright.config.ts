import { defineConfig, devices } from "@playwright/test";

// 针对已运行的 dev 栈（单端口 :80）跑冒烟。
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost",
    headless: true,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
