import { expect, test } from "@playwright/test";

// Contract/UI test: no live backend or model calls.
for (const variant of ["body", "metadata", "degraded"]) {
const metadata = variant === "metadata";
const degraded = variant === "degraded";
test(`source selection, ${variant} and history restoration`, async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("kb_token", `test.${btoa(JSON.stringify({ role: "admin" }))}.test`);
    localStorage.setItem("locale", "zh");
  });
  const agents = [
    { id: "workspace:a", name: "Firewall", description: "PAN-OS configuration", workspace_id: "a", source_type: "workspace" },
    { id: "workspace:b", name: "Finance", description: "Expense policies", workspace_id: "b", source_type: "workspace" },
  ];
  let submitted: Record<string, unknown> | undefined;
  const source = { id: "document:1", citation_id: "S1", doc_id: "doc-1", title: "GlobalProtect setup",
    workspace_name: "Firewall", source_type: "workspace", download_url: "",
    excerpt: metadata ? "Document index: PAN-OS deployment title and summary."
      : "Configure the portal before adding the gateway.",
    content_kind: metadata ? "document_metadata" : "processed_text",
    ...(metadata ? { uploaded_at: "2020-01-01T00:00:00+00:00" } : {}) };
  const question = metadata ? "Which products have documents in the knowledge base?"
    : "How do I configure GlobalProtect?";
  const answer = degraded ? "Useful configuration draft without verified citations." : (metadata ? "**PAN-OS** deployment is documented.[S1]" : "Configure the portal first.[S1]")
    + "\n\n`[S1]` is a code example.";
  const runs = [{ agent_id: "workspace:a", name: "Firewall", status: "done", evidence_count: 1, indexed_count: 233 }];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/chat/stream" && route.request().method() === "POST") {
      submitted = route.request().postDataJSON();
      const events = [
        ["meta", { conversation_id: "conv-1" }],
        ["token", { text: answer }],
        ["done", { conversation_id: "conv-1", answer, sources: degraded ? [] : [source], agent_runs: runs, warning: degraded ? "citation_degraded" : undefined }],
      ];
      await route.fulfill({ contentType: "text/event-stream", body: events.map(([event, data]) =>
        `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("") });
      return;
    }
    let body: unknown = [];
    if (path === "/api/settings/branding") body = { name: "KB-Agent", logo_url: "" };
    if (path === "/api/workspaces") body = agents.map((a) => ({ id: a.workspace_id, name: a.name, role_in_ws: "owner" }));
    if (path === "/api/chat/agents") body = agents;
    if (path === "/api/chat/active") body = { conversation_ids: [] };
    if (path.includes("suggested-questions")) body = { questions: [] };
    if (path === "/api/auth/my-permissions") body = { chat: "admin" };
    if (path === "/api/conversations/conv-1") body = { conversation_id: "conv-1", messages: [
      { role: "user", content: question, sources: [] },
      { role: "assistant", content: answer, sources: degraded ? [] : [source], retrieval: { agent_runs: runs, warning: degraded ? "citation_degraded" : undefined } },
    ] };
    await route.fulfill({ json: body });
  });
  await page.goto("/chat");
  await expect(page.getByRole("button", { name: /检索能力/ })).toHaveCount(0);
  await page.locator("textarea").fill(question);
  await page.locator('button[type="submit"]').click();
  if (degraded) {
    await expect(page.getByText(answer, { exact: true })).toBeVisible();
    const warning = page.getByRole("status");
    await expect(warning).toContainText("来源引用未能通过校验");
    await expect(page.getByRole("button", { name: "[S1]", exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByText(answer, { exact: true })).toBeVisible();
    await expect(warning).toContainText("来源引用未能通过校验");
    return;
  }
  const citation = page.getByRole("button", { name: "[S1]", exact: true });
  await expect(citation).toHaveCount(1);
  expect(submitted).not.toHaveProperty("agent_ids");
  await citation.click();
  await expect(page.getByText(source.excerpt, { exact: true })).toBeVisible();
  await expect(page.getByText(metadata ? "Firewall · 文档信息" : "Firewall · 处理后的正文", { exact: true })).toBeVisible();
  await page.getByText("本轮检索范围", { exact: true }).click();
  await expect(page.getByText("Firewall · 1 条证据 · 已扫描 233 篇文档索引", { exact: true })).toBeVisible();
  await page.reload();
  await expect(citation).toBeVisible();
  await citation.click();
  await expect(page.getByText(source.excerpt, { exact: true })).toBeVisible();
  await page.screenshot({ path: process.env.AGENT_SCREENSHOT || "test-results/chat-agents.png", fullPage: true });
});
}
