import { expect, test } from "@playwright/test";

for (const mobile of [false, true]) {
  test(`external source selection, citations and persistence (${mobile ? "mobile" : "desktop"})`, async ({ page }) => {
    if (mobile) await page.setViewportSize({ width: 430, height: 932 });
    await page.addInitScript(() => {
      localStorage.setItem("kb_token", `test.${btoa(JSON.stringify({ role: "admin" }))}.test`);
      localStorage.setItem("locale", "zh");
    });
    const sources = [
      { id: "kb:1", citation_id: "S1", source_type: "paloalto_kb", title: "Configure gateway certificates",
        url: "https://knowledgebase.paloaltonetworks.com/KCSArticleDetail?id=example",
        excerpt: "Official KB certificate procedure.", content_kind: "web_page", version: "11.1",
        retrieved_at: "2026-11-06T08:00:00Z", updated_at: "2025-01-31T23:40:10Z" },
      { id: "live:1", citation_id: "S2", source_type: "paloalto_live", title: "Community gateway discussion",
        url: "https://live.paloaltonetworks.com/t5/general-topics/example/m-p/123",
        excerpt: "Community certificate experience.", content_kind: "indexed_web_page",
        indexed_at: "2026-11-04T08:00:00Z", retrieved_at: "2026-11-06T08:00:00Z" },
      { id: "docs:1", citation_id: "S3", source_type: "paloalto_docs", title: "GlobalProtect portal authentication",
        url: "https://docs.paloaltonetworks.com/pan-os/11-2/admin/globalprotect",
        excerpt: "Official product documentation for PAN-OS 11.2.", content_kind: "indexed_web_page",
        version: "11.2", indexed_at: "2026-11-04T08:00:00Z", retrieved_at: "2026-11-06T08:00:00Z" },
    ];
    const agents = [{ id: "paloalto_kb", name: "Palo Alto KB", source_type: "paloalto_kb" },
      { id: "paloalto_live", name: "LIVEcommunity", source_type: "paloalto_live" },
      { id: "paloalto_docs", name: "Palo Alto Docs", source_type: "paloalto_docs" }];
    let submitted: Record<string, unknown> | undefined;
    let release = () => {};
    const ready = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/chat/stream" && route.request().method() === "POST") {
        submitted = route.request().postDataJSON();
        await ready;
        const answer = "官方步骤。[S1] 社区经验。[S2] 产品文档。[S3]";
        await route.fulfill({ contentType: "text/event-stream", body: [
          ["meta", { conversation_id: "conv-ext" }],
          ["done", { conversation_id: "conv-ext", answer, sources,
            agent_runs: agents.map((a) => ({ agent_id: a.id, name: a.name, status: "done", evidence_count: 1 })) }],
        ].map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("") });
        return;
      }
      let body: unknown = [];
      if (path === "/api/settings/branding") body = { name: "KB-Agent", logo_url: "" };
      if (path === "/api/chat/agents") body = agents;
      if (path === "/api/workspaces") body = [{ id: "ws-1", name: "Firewall", role_in_ws: "owner" }];
      if (path === "/api/auth/my-permissions") body = { chat: "admin" };
      if (path === "/api/chat/active") body = { conversation_ids: [] };
      if (path.includes("suggested-questions")) body = { questions: [] };
      await route.fulfill({ json: body });
    });
    await page.goto("/chat");
    const picker = page.getByRole("group", { name: "检索来源" });
    const workspace = page.getByRole("checkbox", { name: "空间文档" });
    const kb = page.getByRole("checkbox", { name: "Palo Alto KB" });
    const live = page.getByRole("checkbox", { name: "LIVEcommunity" });
    const docs = page.getByRole("checkbox", { name: "Palo Alto Docs" });
    const scope = page.getByRole("combobox", { name: "空间" });
    await expect(workspace).toBeChecked();
    await expect(kb).not.toBeChecked();
    await expect(live).not.toBeChecked();
    await expect(docs).not.toBeChecked();
    await scope.selectOption("ws-1");
    await kb.check();
    await live.check();
    await docs.check();
    await workspace.uncheck();
    await expect(scope).toBeDisabled();
    await workspace.check();
    await expect(scope).toBeEnabled();
    const areaBox = await picker.boundingBox();
    const inputBox = await page.locator("textarea").boundingBox();
    if (mobile) expect(areaBox?.width).toBeGreaterThan(350);
    expect(areaBox && inputBox && areaBox.y + areaBox.height <= inputBox.y).toBeTruthy();
    await page.locator("textarea").fill("如何配置多个 GlobalProtect 网关的证书？");
    await page.locator('button[type="submit"]').click();
    try {
      await expect.poll(() => submitted).toBeDefined();
      expect(submitted?.workspace_id).toBe("ws-1");
      expect(submitted?.retrieval_sources).toEqual(["paloalto_kb", "paloalto_live", "paloalto_docs", "workspace"]);
      await expect(kb).toBeDisabled();
      await expect(docs).toBeDisabled();
      await expect(scope).toBeDisabled();
    } finally { release(); }
    await expect(page.getByRole("button", { name: "[S1]", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "[S1]", exact: true }).click();
    await expect(page.getByText(sources[0].excerpt, { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "打开来源" })).toHaveAttribute("href", sources[0].url);
    await page.getByRole("button", { name: "[S2]", exact: true }).click();
    await expect(page.getByText("LIVEcommunity · 社区内容 · 官网索引正文", { exact: true })).toBeVisible();
    await expect(page.getByText("索引时间: 2026-11-04T08:00:00Z", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "打开来源" })).toHaveAttribute("href", sources[1].url);
    await page.getByRole("button", { name: "[S3]", exact: true }).click();
    await expect(page.getByRole("region", { name: "[S3] GlobalProtect portal authentication" })).toBeInViewport();
    await expect(page.getByText("Palo Alto Docs · 官方文档 · 11.2 · 官网索引正文", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "打开来源" })).toHaveAttribute("href", sources[2].url);
    await page.reload();
    await expect(kb).toBeChecked();
    await expect(live).toBeChecked();
    await expect(docs).toBeChecked();
    await expect(scope).toHaveValue("ws-1");
    await page.getByRole("button", { name: "[S3]", exact: true }).click();
    await expect(page.getByText(sources[2].excerpt, { exact: true })).toBeVisible();
    await page.screenshot({ path: `${process.env.EXTERNAL_SCREENSHOT_DIR || "test-results"}/chat-external-${mobile ? "mobile" : "desktop"}.png`, fullPage: true });
  });
}
