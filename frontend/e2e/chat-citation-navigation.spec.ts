import { expect, test } from "@playwright/test";

test.use({ reducedMotion: "reduce" });

test("citations expand and scroll to the right evidence in long answers and repeated turns", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("kb_token", `test.${btoa(JSON.stringify({ role: "admin" }))}.test`);
    localStorage.setItem("locale", "zh");
    const answer = "结论一。[S1] 结论二。[S2]\n\n" + "长回答内容。\n\n".repeat(80);
    const sources = (prefix: string) => [1, 2].map((n) => ({
      id: `${prefix}-${n}`, citation_id: `S${n}`, title: `${prefix} source ${n}`,
      excerpt: `${prefix} evidence ${n}\n`.repeat(80), content_kind: "processed_text",
      workspace_name: "Firewall", source_type: "workspace", download_url: "",
    }));
    sessionStorage.setItem("chat_state", JSON.stringify({
      workspaceId: null, conversationId: "conv-1", turns: [
        { role: "user", content: "第一个问题" },
        { role: "assistant", content: answer, sources: sources("First") },
        { role: "user", content: "第二个问题" },
        { role: "assistant", content: answer, sources: sources("Second") },
      ],
    }));
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path === "/api/settings/branding") body = { name: "KB-Agent", logo_url: "" };
    if (path === "/api/auth/my-permissions") body = { chat: "admin" };
    if (path === "/api/chat/active") body = { conversation_ids: [] };
    if (path.includes("suggested-questions")) body = { questions: [] };
    await route.fulfill({ json: body });
  });
  await page.goto("/chat");
  const firstS1 = page.getByRole("button", { name: "[S1]", exact: true }).first();
  await firstS1.click();
  const firstPanel = page.getByRole("region", { name: "[S1] First source 1", exact: true });
  await expect(firstPanel).toBeFocused();
  await expect(firstPanel).toBeInViewport({ ratio: 0.9 });
  await expect(firstS1).toHaveAttribute("aria-expanded", "true");
  await expect(firstS1).toHaveAttribute("aria-controls", (await firstPanel.getAttribute("id"))!);
  await expect(firstS1).not.toBeInViewport();

  // Even an already expanded citation must jump back and reset its inner excerpt.
  await firstPanel.locator("blockquote").evaluate((node) => { node.scrollTop = 200; });
  await firstS1.click();
  await expect(firstPanel).toBeInViewport({ ratio: 0.9 });
  await expect.poll(() => firstPanel.locator("blockquote").evaluate((node) => node.scrollTop)).toBe(0);

  await page.getByRole("button", { name: "[S2]", exact: true }).first().click();
  const other = page.getByRole("region", { name: "[S2] First source 2", exact: true });
  await expect(other).toBeFocused();
  await expect(other).toBeInViewport({ ratio: 0.9 });
  await expect(firstPanel).toHaveCount(0);

  // S1 in another answer must reveal that answer's source, not the earlier S1.
  await page.getByRole("button", { name: "[S1]", exact: true }).nth(1).click();
  const secondPanel = page.getByRole("region", { name: "[S1] Second source 1", exact: true });
  await expect(secondPanel).toBeFocused();
  await expect(secondPanel).toBeInViewport({ ratio: 0.9 });
  expect(await secondPanel.getAttribute("id")).not.toBe(await other.getAttribute("id"));
  await expect(other).not.toBeInViewport();
});
