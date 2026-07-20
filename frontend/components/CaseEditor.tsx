"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import { useTranslations } from "next-intl";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Placeholder } from "@tiptap/extensions";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";

export interface CaseEditorHandle {
  getJSON: () => object;
  getHTML: () => string;
  isEmpty: () => boolean;
}

// 单张内嵌图片上限（base64，防 payload 过大）
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

const CaseEditor = forwardRef<CaseEditorHandle, { onImageError?: () => void }>(
  function CaseEditor({ onImageError }, ref) {
    const t = useTranslations("caseEntry");
    const fileRef = useRef<HTMLInputElement>(null);
    // editorProps 在 useEditor 求值时 editor 尚不存在，粘贴/拖拽回调经 ref 拿实例
    const editorRef = useRef<ReturnType<typeof useEditor>>(null);

    // 把图片文件转 base64 内嵌（粘贴/拖拽/选择共用）。at 为可选插入位置。
    // 返回 true 表示已消费该文件（无论成功还是因超限被拒）。
    function insertImageFile(file: File, at?: number): boolean {
      if (!file.type.startsWith("image/")) return false;
      if (file.size > MAX_IMAGE_BYTES) {
        onImageError?.();
        return true;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const src = typeof reader.result === "string" ? reader.result : "";
        const ed = editorRef.current;
        if (!src || !ed) return;
        if (typeof at === "number") {
          ed.chain().focus().insertContentAt(at, { type: "image", attrs: { src } }).run();
        } else {
          ed.chain().focus().setImage({ src }).run();
        }
      };
      reader.readAsDataURL(file);
      return true;
    }

    const editor = useEditor({
      extensions: [
        // StarterKit v3 已内置 Link；关掉它，改用下面单独配置的 Link，避免重复扩展
        StarterKit.configure({ link: false }),
        Image.configure({ inline: false }),
        Link.configure({ openOnClick: false, autolink: true }),
        Placeholder.configure({ placeholder: t("editorPlaceholder") }),
      ],
      content: "",
      immediatelyRender: false,
      editorProps: {
        // 粘贴：剪贴板里有图片项时转 base64 内嵌；否则放行默认（文本/富文本）粘贴
        handlePaste: (_view, event) => {
          const items = event.clipboardData?.items;
          if (!items) return false;
          for (const item of Array.from(items)) {
            if (item.type.startsWith("image/")) {
              const file = item.getAsFile();
              if (file) {
                insertImageFile(file);
                return true; // 消费该粘贴，阻止默认行为
              }
            }
          }
          return false;
        },
        // 拖拽：把拖入的图片文件转 base64 内嵌到落点位置
        handleDrop: (view, event) => {
          const dt = (event as DragEvent).dataTransfer;
          const files = dt?.files;
          if (!files || files.length === 0) return false;
          const images = Array.from(files).filter((f) => f.type.startsWith("image/"));
          if (images.length === 0) return false;
          event.preventDefault();
          const pos = view.posAtCoords({
            left: (event as DragEvent).clientX,
            top: (event as DragEvent).clientY,
          })?.pos;
          images.forEach((f) => insertImageFile(f, pos));
          return true;
        },
        attributes: {
          // 不依赖 @tailwindcss/typography(prose)——用 arbitrary variants 显式给
          // 标题/列表/链接上样式，否则 H1/H2 与正文视觉无区别，误以为"选不上"。
          // 更舒展的行高 + 深色 caret，接近在线文档观感。
          class: [
            "min-h-[60vh] px-10 py-8 text-[15px] leading-7 text-gray-800 caret-slate-800 focus:outline-none",
            "[&_h1]:text-3xl [&_h1]:font-bold [&_h1]:mt-6 [&_h1]:mb-3 [&_h1]:leading-tight",
            "[&_h2]:text-2xl [&_h2]:font-bold [&_h2]:mt-5 [&_h2]:mb-2.5 [&_h2]:leading-snug",
            "[&_h3]:text-lg [&_h3]:font-semibold [&_h3]:mt-4 [&_h3]:mb-2",
            "[&_p]:my-2.5",
            "[&_ul]:list-disc [&_ul]:pl-7 [&_ul]:my-2.5",
            "[&_ol]:list-decimal [&_ol]:pl-7 [&_ol]:my-2.5",
            "[&_li]:my-1 [&_li]:pl-1",
            "[&_a]:text-blue-600 [&_a]:underline",
            "[&_strong]:font-bold [&_em]:italic",
            "[&_img]:max-w-full [&_img]:rounded-md [&_img]:my-3 [&_img]:shadow-sm",
            // 占位符（Placeholder 扩展给空节点加 is-empty + data-placeholder）
            "[&_.is-editor-empty:first-child]:before:content-[attr(data-placeholder)]",
            "[&_.is-editor-empty:first-child]:before:text-gray-300 [&_.is-editor-empty:first-child]:before:float-left",
            "[&_.is-editor-empty:first-child]:before:h-0 [&_.is-editor-empty:first-child]:before:pointer-events-none",
          ].join(" "),
        },
      },
    });
    editorRef.current = editor;

    useImperativeHandle(
      ref,
      () => ({
        getJSON: () => editor?.getJSON() ?? { type: "doc", content: [] },
        getHTML: () => editor?.getHTML() ?? "",
        isEmpty: () => editor?.isEmpty ?? true,
      }),
      [editor]
    );

    if (!editor) return null;

    function pickImage() {
      fileRef.current?.click();
    }

    function onImageSelected(e: React.ChangeEvent<HTMLInputElement>) {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (file) insertImageFile(file);
    }

    function addLink() {
      const prev = editor!.getAttributes("link").href as string | undefined;
      const url = window.prompt(t("linkPrompt"), prev ?? "https://");
      if (url === null) return;
      if (url === "") {
        editor!.chain().focus().extendMarkRange("link").unsetLink().run();
        return;
      }
      editor!.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    }

    const Btn = ({
      onClick,
      active,
      label,
    }: {
      onClick: () => void;
      active?: boolean;
      label: string;
    }) => (
      <button
        type="button"
        onClick={onClick}
        className={`rounded px-2 py-1 text-xs transition-colors ${
          active
            ? "bg-blue-100 text-blue-700"
            : "text-gray-600 hover:bg-gray-100"
        }`}
      >
        {label}
      </button>
    );

    return (
      <div className="overflow-hidden rounded-xl border border-gray-200 bg-gray-100 shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-blue-100">
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-0.5 border-b border-gray-200 bg-white/95 px-3 py-2 backdrop-blur">
          <Btn
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            active={editor.isActive("heading", { level: 1 })}
            label={t("tb_h1")}
          />
          <Btn
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            active={editor.isActive("heading", { level: 2 })}
            label={t("tb_h2")}
          />
          <Btn
            onClick={() => editor.chain().focus().setParagraph().run()}
            active={editor.isActive("paragraph")}
            label={t("tb_paragraph")}
          />
          <span className="mx-1 h-4 w-px bg-gray-200" />
          <Btn
            onClick={() => editor.chain().focus().toggleBold().run()}
            active={editor.isActive("bold")}
            label={t("tb_bold")}
          />
          <Btn
            onClick={() => editor.chain().focus().toggleItalic().run()}
            active={editor.isActive("italic")}
            label={t("tb_italic")}
          />
          <span className="mx-1 h-4 w-px bg-gray-200" />
          <Btn
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            active={editor.isActive("bulletList")}
            label={t("tb_bullet")}
          />
          <Btn
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            active={editor.isActive("orderedList")}
            label={t("tb_ordered")}
          />
          <span className="mx-1 h-4 w-px bg-gray-200" />
          <Btn onClick={addLink} active={editor.isActive("link")} label={t("tb_link")} />
          <Btn onClick={pickImage} label={t("tb_image")} />
          <span className="mx-1 h-4 w-px bg-gray-200" />
          <Btn onClick={() => editor.chain().focus().undo().run()} label={t("tb_undo")} />
          <Btn onClick={() => editor.chain().focus().redo().run()} label={t("tb_redo")} />
        </div>
        {/* 纸张：灰底上居中的白色文档卡片 */}
        <div className="max-h-[70vh] overflow-y-auto p-6">
          <div className="mx-auto max-w-3xl rounded-lg bg-white shadow-md ring-1 ring-gray-200">
            <EditorContent editor={editor} />
          </div>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={onImageSelected}
        />
      </div>
    );
  }
);

export default CaseEditor;
