// 解析聊天+「交互模式」下模型输出的 ```ask-user 围栏 JSON 块。
// 该块经普通 token 流传出、随消息 content 落库；此处从正文剥离并结构化。
// 任何非法/半截块一律降级为纯文本（ask=null），绝不抛错阻断对话。

export interface AskUserOption {
  label: string;
  description?: string;
}

export interface AskUserPayload {
  question: string;
  options: AskUserOption[];
  multiSelect?: boolean;
}

export interface ParsedAskUser {
  clean: string; // 剥除 ask-user 块后的正文（供 Markdown 渲染）
  ask: AskUserPayload | null;
}

// 匹配 ```ask-user\n{...}\n``` 围栏块（容忍前后空白、大小写）
const ASK_USER_RE = /```ask-user\s*\n([\s\S]*?)\n?```/i;

function sanitize(raw: unknown): AskUserPayload | null {
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Record<string, unknown>;
  if (typeof obj.question !== "string" || !obj.question.trim()) return null;
  if (!Array.isArray(obj.options)) return null;

  const options: AskUserOption[] = [];
  for (const o of obj.options) {
    if (typeof o !== "object" || o === null) continue;
    const opt = o as Record<string, unknown>;
    if (typeof opt.label !== "string" || !opt.label.trim()) continue;
    options.push({
      label: opt.label.slice(0, 200),
      description:
        typeof opt.description === "string" ? opt.description.slice(0, 300) : undefined,
    });
    if (options.length >= 4) break; // 最多 4 项，防畸形输出撑爆布局
  }
  if (options.length === 0) return null;

  return {
    question: obj.question.slice(0, 500),
    options,
    multiSelect: obj.multiSelect === true,
  };
}

export function parseAskUser(content: string): ParsedAskUser {
  if (!content) return { clean: content, ask: null };
  const m = content.match(ASK_USER_RE);
  if (!m) return { clean: content, ask: null };
  try {
    const parsed = JSON.parse(m[1]);
    const ask = sanitize(parsed);
    if (!ask) return { clean: content, ask: null };
    const clean = content.replace(m[0], "").trim();
    return { clean, ask };
  } catch {
    // 半截或非法 JSON（如流式未结束）→ 原样显示
    return { clean: content, ask: null };
  }
}
