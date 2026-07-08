"use client";

import ReactMarkdown from "react-markdown";

// LLM 产物的 Markdown 渲染。react-markdown 默认不解析裸 HTML，
// 且未启用 rehype-raw，故不会执行 <script> 等 —— 天然防存储型 XSS（SECURITY #6）。
export default function Markdown({ content }: { content: string }) {
  return (
    <div className="max-w-none space-y-3 break-words text-sm leading-relaxed">
      <ReactMarkdown
        components={{
          // 链接强制新窗口 + noopener，避免 tabnabbing
          a: ({ ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline"
            />
          ),
          p: ({ ...props }) => <p className="leading-relaxed" {...props} />,
          ul: ({ ...props }) => (
            <ul className="ml-5 list-disc space-y-1.5" {...props} />
          ),
          ol: ({ ...props }) => (
            <ol className="ml-5 list-decimal space-y-1.5" {...props} />
          ),
          li: ({ ...props }) => <li className="leading-relaxed" {...props} />,
          h1: ({ ...props }) => (
            <h1 className="mt-2 text-base font-semibold" {...props} />
          ),
          h2: ({ ...props }) => (
            <h2 className="mt-2 text-base font-semibold" {...props} />
          ),
          h3: ({ ...props }) => (
            <h3 className="mt-1 text-sm font-semibold" {...props} />
          ),
          code: ({ ...props }) => (
            <code
              className="rounded bg-gray-100 px-1 py-0.5 text-[0.85em]"
              {...props}
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
