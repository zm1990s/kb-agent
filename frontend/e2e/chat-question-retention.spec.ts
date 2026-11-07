import { expect, test, type Page } from "@playwright/test";

const question = "知识库里有哪些产品的文档？";
const answer = "示例回答：知识库包含产品配置文档。";

async function mockChat(page: Page, restorePending = false) {
  await page.addInitScript(({ pending, question }) => {
    localStorage.setItem("kb_token", `test.${btoa(JSON.stringify({ role: "admin" }))}.test`);
    localStorage.setItem("locale", "zh");
    if (pending && !sessionStorage.getItem("chat_state")) {
      sessionStorage.setItem("chat_state", JSON.stringify({
        workspaceId: null, conversationId: "conv-1",
        turns: [{ role: "user", content: question }],
      }));
    }
  }, { pending: restorePending, question });
  const submitted: { message: string; conversation_id: string | null }[] = [];
  let release = () => {};
  const responseReady = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/chat/stream" && route.request().method() === "POST") {
      submitted.push(route.request().postDataJSON());
      await responseReady;
      const events = [
        ["meta", { conversation_id: "conv-1" }],
        ["token", { text: answer }],
        ["done", { conversation_id: "conv-1", answer, sources: [] }],
      ];
      await route.fulfill({ contentType: "text/event-stream", body: events.map(([event, data]) =>
        `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("") });
      return;
    }
    let body: unknown = [];
    if (path === "/api/settings/branding") body = { name: "KB-Agent", logo_url: "" };
    if (path.includes("suggested-questions")) body = { questions: [question] };
    if (path === "/api/auth/my-permissions") body = { chat: "admin" };
    if (path === "/api/chat/active") body = { conversation_ids: [] };
    if (path === "/api/conversations/conv-1") body = { conversation_id: "conv-1", messages: [
      { role: "user", content: submitted.at(-1)?.message ?? question, sources: [] },
      { role: "assistant", content: answer, sources: [] },
    ] };
    await route.fulfill({ json: body });
  });
  return { submitted, release };
}

for (const entry of ["shortcut", "typed", "retry"] as const) {
  test(`${entry} retains exactly one question during generation, after completion and reload`, async ({ page }) => {
    const chat = await mockChat(page, entry === "retry");
    await page.goto("/chat");
    try {
      if (entry === "shortcut") {
        await page.getByRole("button", { name: question, exact: true }).click();
      } else if (entry === "typed") {
        await page.locator("textarea").fill(question);
        await page.locator('button[type="submit"]').click();
      } else {
        await page.getByRole("button", { name: "重新发送", exact: true }).click();
      }
      await expect.poll(() => chat.submitted.length).toBe(1);
      expect(chat.submitted[0].message).toBe(question);
      await expect(page.getByRole("button", { name: question, exact: true })).toHaveCount(0);
      await expect(page.getByText(question, { exact: true })).toHaveCount(1);
    } finally {
      chat.release();
    }
    await expect(page.getByText(answer, { exact: true })).toBeVisible();
    await expect(page.getByText(question, { exact: true })).toHaveCount(1);
    await expect.poll(() => page.evaluate(() =>
      JSON.parse(sessionStorage.getItem("chat_state")!).turns.map((t: { role: string }) => t.role)
    )).toEqual(["user", "assistant"]);
    await page.reload();
    await expect(page.getByText(question, { exact: true })).toHaveCount(1);
    await expect(page.getByText(answer, { exact: true })).toBeVisible();
  });
}

test("editing a shortcut question replaces the original without duplicating the new question", async ({ page }) => {
  const chat = await mockChat(page);
  chat.release();
  await page.goto("/chat");
  await page.getByRole("button", { name: question, exact: true }).click();
  await expect(page.getByText(answer, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "编辑并重新发送", exact: true }).click();
  const edited = "GlobalProtect 门户如何配置？";
  await page.locator("textarea").first().fill(edited);
  await page.getByRole("button", { name: "重新发送", exact: true }).click();
  await expect.poll(() => chat.submitted.length).toBe(2);
  expect(chat.submitted[1].message).toBe(edited);
  await expect(page.getByText(answer, { exact: true })).toBeVisible();
  await expect(page.getByText(question, { exact: true })).toHaveCount(0);
  await expect(page.getByText(edited, { exact: true })).toHaveCount(1);
  await expect.poll(() => page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("chat_state")!).turns.map((t: { role: string }) => t.role)
  )).toEqual(["user", "assistant"]);
});

test("restoring an old answer-only cache recovers the question from saved history", async ({ page }) => {
  await mockChat(page);
  await page.addInitScript(({ answer }) => {
    sessionStorage.setItem("chat_state", JSON.stringify({
      workspaceId: null, conversationId: "conv-1",
      turns: [{ role: "assistant", content: answer }],
    }));
  }, { answer });
  await page.goto("/chat");
  await expect(page.getByText(question, { exact: true })).toHaveCount(1);
  await expect(page.getByText(answer, { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("chat_state")!).turns.map((t: { role: string }) => t.role)
  )).toEqual(["user", "assistant"]);
});

test("late cache repair does not overwrite a newly started conversation", async ({ page }) => {
  await mockChat(page);
  await page.addInitScript(({ answer }) => {
    sessionStorage.setItem("chat_state", JSON.stringify({
      workspaceId: null, conversationId: "conv-1",
      turns: [{ role: "assistant", content: answer }],
    }));
  }, { answer });
  let release = () => {};
  const historyReady = new Promise<void>((resolve) => { release = resolve; });
  let requested = false;
  await page.route("**/api/conversations/conv-1", async (route) => {
    requested = true;
    await historyReady;
    await route.fulfill({ json: { conversation_id: "conv-1", messages: [
      { role: "user", content: question, sources: [] },
      { role: "assistant", content: answer, sources: [] },
    ] } });
  });
  await page.goto("/chat");
  try {
    await expect.poll(() => requested).toBe(true);
    await page.getByRole("button", { name: "+ 新建会话", exact: true }).click();
    const response = page.waitForResponse("**/api/conversations/conv-1");
    release();
    await response;
    await expect(page.getByRole("button", { name: question, exact: true })).toBeVisible();
    await expect(page.getByText(answer, { exact: true })).toHaveCount(0);
    await expect.poll(() => page.evaluate(() =>
      JSON.parse(sessionStorage.getItem("chat_state")!).turns
    )).toEqual([]);
  } finally {
    release();
  }
});
