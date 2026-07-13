"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// LLM 产物的 Markdown 渲染。react-markdown 默认不解析裸 HTML，
// 且未启用 rehype-raw，故不会执行 <script> 等 —— 天然防存储型 XSS（SECURITY #6）。
export default function Markdown({ content }: { content: string }) {
  // 兜底：LLM 有时输出字面量 \n 而非真实换行，导致 Markdown 解析失败
  const normalized = content.replace(/\\n/g, "\n").replace(/\\t/g, "\t");
  return (
    <div className="max-w-none break-words text-sm leading-relaxed text-gray-900">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, ...props }) => {
            const safe = href && /^(https?:\/\/|mailto:|\/)/i.test(href) ? href : undefined;
            return (
              <a
                {...props}
                href={safe}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 underline hover:text-blue-700"
              />
            );
          },
          p: ({ ...props }) => <p className="my-1 leading-relaxed" {...props} />,
          ul: ({ ...props }) => <ul className="my-1 ml-5 list-disc space-y-1" {...props} />,
          ol: ({ ...props }) => <ol className="my-1 ml-5 list-decimal space-y-1" {...props} />,
          li: ({ ...props }) => <li className="leading-relaxed" {...props} />,
          h1: ({ ...props }) => <h1 className="mt-3 mb-1 text-base font-semibold text-gray-900" {...props} />,
          h2: ({ ...props }) => <h2 className="mt-3 mb-1 text-base font-semibold text-gray-900" {...props} />,
          h3: ({ ...props }) => <h3 className="mt-2 mb-1 text-sm font-semibold text-gray-900" {...props} />,
          code: ({ ...props }) => (
            <code
              className="rounded bg-gray-100 px-1.5 py-0.5 text-xs font-mono text-pink-600"
              {...props}
            />
          ),
          pre: ({ ...props }) => (
            <pre
              className="my-2 overflow-x-auto rounded-lg border border-gray-200 bg-gray-900 p-4 text-xs text-gray-100"
              {...props}
            />
          ),
          blockquote: ({ ...props }) => (
            <blockquote className="my-2 border-l-4 border-gray-300 pl-4 text-gray-600 italic" {...props} />
          ),
          table: ({ ...props }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-xs" {...props} />
            </div>
          ),
          th: ({ ...props }) => (
            <th className="border border-gray-300 bg-gray-50 px-3 py-1.5 text-left font-semibold" {...props} />
          ),
          td: ({ ...props }) => (
            <td className="border border-gray-200 px-3 py-1.5" {...props} />
          ),
        }}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
