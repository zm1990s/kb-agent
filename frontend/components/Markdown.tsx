"use client";

import ReactMarkdown from "react-markdown";

// LLM 产物的 Markdown 渲染。react-markdown 默认不解析裸 HTML，
// 且未启用 rehype-raw，故不会执行 <script> 等 —— 天然防存储型 XSS（SECURITY #6）。
export default function Markdown({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none break-words">
      <ReactMarkdown
        components={{
          // 链接强制新窗口 + noopener，避免 tabnabbing
          a: ({ ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
