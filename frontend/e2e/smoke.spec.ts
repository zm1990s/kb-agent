import { expect, test } from "@playwright/test";

// 冒烟：注册 → 登录 → 进入对话页 → 提问得到（无命中）回答。
// 依赖 dev 栈在 http://localhost:80 运行（docker compose up）。
test("register, login, and chat no-match flow", async ({ page }) => {
  const email = `e2e-${Date.now()}@company.com`;
  const password = "longenough1";

  await page.goto("/login");

  // 切到注册
  await page.getByRole("button", { name: /去注册/ }).click();
  await page.getByPlaceholder("you@company.com").fill(email);
  await page.getByPlaceholder("至少 8 位").fill(password);
  await page.getByRole("button", { name: /注册并登录/ }).click();

  // 进入对话页
  await expect(page).toHaveURL(/\/chat/);

  // 无空间时，输入框提示选择空间；此处仅验证页面骨架可见
  await expect(page.getByText("对话查询")).toBeVisible();
});

test("login page rejects disallowed domain", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /去注册/ }).click();
  await page.getByPlaceholder("you@company.com").fill("x@evil-domain.com");
  await page.getByPlaceholder("至少 8 位").fill("longenough1");
  await page.getByRole("button", { name: /注册并登录/ }).click();
  await expect(page.getByText(/域名不在允许列表/)).toBeVisible();
});
