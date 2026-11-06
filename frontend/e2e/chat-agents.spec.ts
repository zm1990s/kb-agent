import { expect, test } from "@playwright/test";

// Contract/UI test: no live backend or model calls.
test("source selection, inline evidence and history restoration", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("kb_token", `test.${btoa(JSON.stringify({ role: "admin" }))}.test`);
    localStorage.setItem("locale", "en");
  });
  const agents = [
    { id: "workspace:a", name: "Firewall", description: "PAN-OS configuration", workspace_id: "a", source_type: "workspace" },
    { id: "workspace:b", name: "Finance", description: "Expense policies", workspace_id: "b", source_type: "workspace" },
  ];
  let submitted: Record<string, unknown> | undefined;
  const source = { id: "document:1", citation_id: "S1", doc_id: "doc-1", title: "GlobalProtect setup",
    workspace_name: "Firewall", source_type: "workspace", download_url: "",
    excerpt: "Configure the portal before adding the gateway.", content_kind: "processed_text" };
  const answer = "Configure the portal first.[S1]\n\n`[S1]` is a code example.";
  const runs = [{ agent_id: "workspace:a", name: "Firewall", status: "done", evidence_count: 1 }];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/chat/stream" && route.request().method() === "POST") {
      submitted = route.request().postDataJSON();
      const events = [
        ["meta", { conversation_id: "conv-1" }],
        ["token", { text: answer }],
        ["done", { conversation_id: "conv-1", answer, sources: [source], agent_runs: runs }],
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
      { role: "user", content: "How do I configure GlobalProtect?", sources: [] },
      { role: "assistant", content: answer, sources: [source], retrieval: { agent_runs: runs } },
    ] };
    await route.fulfill({ json: body });
  });
  await page.goto("/chat");
  await page.getByText("Sources · Auto", { exact: true }).click();
  await page.getByRole("checkbox", { name: "Finance Expense policies" }).uncheck();
  await page.getByText("Sources · 1", { exact: true }).click();
  await page.locator("textarea").fill("How do I configure GlobalProtect?");
  await page.locator('button[type="submit"]').click();
  const citation = page.getByRole("button", { name: "[S1]", exact: true });
  await expect(citation).toHaveCount(1);
  expect(submitted?.agent_ids).toEqual(["workspace:a"]);
  await citation.click();
  await expect(page.getByText(source.excerpt, { exact: true })).toBeVisible();
  await expect(page.getByText("Firewall · Processed text", { exact: true })).toBeVisible();
  await page.getByText("Retrieval scope", { exact: true }).click();
  await expect(page.getByText("Firewall · 1 evidence items", { exact: true })).toBeVisible();
  await page.reload();
  await expect(citation).toBeVisible();
  await citation.click();
  await expect(page.getByText(source.excerpt, { exact: true })).toBeVisible();
  await page.screenshot({ path: process.env.AGENT_SCREENSHOT || "test-results/chat-agents.png", fullPage: true });
});
