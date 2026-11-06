import { expect, test } from "@playwright/test";

for (const mobile of [false, true]) {
  test(`live agent branches reflect stream snapshots (${mobile ? "mobile" : "desktop"})`, async ({ page }) => {
    await page.setViewportSize({ width: mobile ? 430 : 1440, height: 1000 });
    await page.addInitScript(() => {
      localStorage.setItem("kb_token", `test.${btoa(JSON.stringify({ role: "admin" }))}.test`);
      localStorage.setItem("locale", "zh");
      sessionStorage.setItem("chat_state", JSON.stringify({ workspaceId: null, turns: [],
        retrievalSources: ["workspace", "paloalto_kb", "paloalto_live", "paloalto_docs"] }));
      // Keep an actual ReadableStream open so the app's SSE parser receives live
      // snapshots one at a time, without using a real model or business data.
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input, init) => {
        if (String(input) !== "/api/chat/stream") return originalFetch(input, init);
        const encoder = new TextEncoder();
        return new Response(new ReadableStream({
          start(controller) {
            const receive = (event: Event) => {
              const { kind, data } = (event as CustomEvent).detail;
              controller.enqueue(encoder.encode(`event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`));
              if (kind === "done") {
                window.removeEventListener("test-agent-event", receive);
                controller.close();
              }
            };
            window.addEventListener("test-agent-event", receive);
          },
        }), { headers: { "Content-Type": "text/event-stream" } });
      };
    });
    const agents = [
      { id: "workspace:1", name: "Firewall", source_type: "workspace", workspace_id: "1" },
      { id: "paloalto_kb", name: "Palo Alto KB", source_type: "paloalto_kb" },
      { id: "paloalto_live", name: "LIVEcommunity", source_type: "paloalto_live" },
      { id: "paloalto_docs", name: "Palo Alto Docs", source_type: "paloalto_docs" },
    ];
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let body: unknown = [];
      if (path === "/api/chat/agents") body = agents;
      if (path === "/api/workspaces") body = [{ id: "1", name: "Firewall", role_in_ws: "owner" }];
      if (path === "/api/settings/branding") body = { name: "KB-Agent", logo_url: "" };
      if (path === "/api/auth/my-permissions") body = { chat: "admin" };
      if (path === "/api/chat/active") body = { conversation_ids: [] };
      if (path.includes("suggested-questions")) body = { questions: [] };
      await route.fulfill({ json: body });
    });
    await page.goto("/chat");
    await expect(page.getByRole("checkbox", { name: "Palo Alto Docs" })).toBeChecked();
    await page.locator("textarea").fill("如何配置 GlobalProtect 网关？");
    await page.locator('button[type="submit"]').click();
    const panel = page.getByRole("region", { name: "多 Agent 协作" });
    await expect(panel).toBeVisible();
    await expect(panel.getByText("等待启动", { exact: true })).toHaveCount(4);
    const sendStage = async (statuses: string[], stage = "indexing") => {
      await page.evaluate(({ statuses, agents, stage }) => {
        window.dispatchEvent(new CustomEvent("test-agent-event", { detail: { kind: "stage", data: {
          stage, message_key: "stage_agent_activity", message_params: {},
          agent_runs: agents.map((a, i) => ({ agent_id: a.id, name: a.name, source_type: a.source_type,
            status: statuses[i], evidence_count: i === 0 ? 3 : 0 })),
        } } }));
      }, { statuses, agents, stage });
    };
    await sendStage(["running", "running", "running", "queued"]);
    await expect(panel.getByRole("status")).toContainText("3 个 Agent 运行中");
    await expect(panel.locator('[data-state="running"]')).toHaveCount(3);
    await sendStage(["done", "running", "failed", "running"]);
    await expect(panel.getByText("找到 3 条证据")).toBeVisible();
    await expect(panel.getByText("检索未完成", { exact: true })).toBeVisible();
    await expect(panel.locator('[data-state="running"]')).toHaveCount(2);
    expect(await panel.evaluate((node) => node.getAnimations({ subtree: true }).length)).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await panel.screenshot({ path: `${process.env.AGENT_PROGRESS_SCREENSHOTS || "test-results"}/agent-progress-${mobile ? "mobile" : "desktop"}.png` });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect.poll(() => panel.evaluate((node) => node.getAnimations({ subtree: true }).length)).toBe(0);
    await sendStage(["done", "done", "failed", "done"], "thinking");
    await expect(panel.getByText("未找到相关证据", { exact: true })).toHaveCount(2);
    await expect(panel.locator('[data-state="running"]')).toHaveCount(0);
    await expect(panel.getByRole("status")).toContainText("正在综合证据与回答");
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-agent-event", { detail: {
      kind: "done", data: { conversation_id: "progress-conv", answer: "已完成检索。", sources: [] },
    } })));
    await expect(panel).toHaveCount(0);
    await expect(page.getByText("已完成检索。", { exact: true })).toBeVisible();
  });
}
