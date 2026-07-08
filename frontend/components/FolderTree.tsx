"use client";

import { useState } from "react";
import type { Folder } from "@/lib/types";

export interface FolderNode extends Folder {
  children: FolderNode[];
}

// 把扁平 folders 组装成树。
export function buildTree(folders: Folder[]): FolderNode[] {
  const byId = new Map<string, FolderNode>();
  folders.forEach((f) => byId.set(f.id, { ...f, children: [] }));
  const roots: FolderNode[] = [];
  byId.forEach((node) => {
    if (node.parent_id && byId.has(node.parent_id)) {
      byId.get(node.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  });
  const sortRec = (nodes: FolderNode[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name));
    nodes.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}

interface Props {
  nodes: FolderNode[];
  activeId: string;
  admin: boolean;
  depth?: number;
  onSelect: (id: string) => void;
  onAddChild: (parentId: string) => void;
  onRename: (folder: Folder) => void;
  onDelete: (id: string) => void;
  // 拖拽落到目录节点：payload 形如 {type:'doc'|'folder', id}
  onDropItem?: (targetFolderId: string | null, payload: DragPayload) => void;
}

export interface DragPayload {
  type: "doc" | "folder";
  id: string;
}

// 递归渲染文件夹树。每个节点可展开/折叠，管理员可建子目录/改名/删除。
export default function FolderTree({
  nodes,
  activeId,
  admin,
  depth = 0,
  onSelect,
  onAddChild,
  onRename,
  onDelete,
  onDropItem,
}: Props) {
  return (
    <div>
      {nodes.map((node) => (
        <FolderRow
          key={node.id}
          node={node}
          activeId={activeId}
          admin={admin}
          depth={depth}
          onSelect={onSelect}
          onAddChild={onAddChild}
          onRename={onRename}
          onDelete={onDelete}
          onDropItem={onDropItem}
        />
      ))}
    </div>
  );
}

function FolderRow({
  node,
  activeId,
  admin,
  depth,
  onSelect,
  onAddChild,
  onRename,
  onDelete,
  onDropItem,
}: { node: FolderNode; depth: number } & Omit<Props, "nodes" | "depth">) {
  const [open, setOpen] = useState(true);
  const [dragOver, setDragOver] = useState(false);
  const hasChildren = node.children.length > 0;

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const raw = e.dataTransfer.getData("application/kb-item");
    if (!raw || !onDropItem) return;
    try {
      const payload = JSON.parse(raw) as DragPayload;
      if (payload.type === "folder" && payload.id === node.id) return; // 不能拖到自己
      onDropItem(node.id, payload);
    } catch {
      /* ignore */
    }
  }

  return (
    <div>
      <div
        className={`group flex items-center rounded ${
          dragOver
            ? "ring-2 ring-blue-400"
            : activeId === node.id
              ? "bg-blue-50"
              : "hover:bg-gray-100"
        }`}
        style={{ paddingLeft: depth * 12 }}
        onDragOver={(e) => {
          if (onDropItem) {
            e.preventDefault();
            setDragOver(true);
          }
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <button
          onClick={() => setOpen((o) => !o)}
          className="w-4 shrink-0 text-xs text-gray-400"
          aria-label={open ? "折叠" : "展开"}
        >
          {hasChildren ? (open ? "▾" : "▸") : ""}
        </button>
        <button
          onClick={() => onSelect(node.id)}
          draggable={admin && !!onDropItem}
          onDragStart={(e) =>
            e.dataTransfer.setData(
              "application/kb-item",
              JSON.stringify({ type: "folder", id: node.id })
            )
          }
          className={`flex-1 cursor-grab truncate py-2 pr-1 text-left text-sm active:cursor-grabbing ${
            activeId === node.id ? "text-blue-700" : "text-gray-600"
          }`}
        >
          📁 {node.name}
        </button>
        {admin && (
          <span className="hidden shrink-0 gap-1 pr-1 text-xs group-hover:flex">
            <button
              onClick={() => onAddChild(node.id)}
              className="text-gray-400 hover:text-blue-600"
              title="新建子目录"
            >
              ＋
            </button>
            <button
              onClick={() => onRename(node)}
              className="text-gray-400 hover:text-blue-600"
              title="重命名"
            >
              ✎
            </button>
            <button
              onClick={() => onDelete(node.id)}
              className="text-gray-400 hover:text-red-600"
              title="删除目录"
            >
              ✕
            </button>
          </span>
        )}
      </div>
      {open && hasChildren && (
        <FolderTree
          nodes={node.children}
          activeId={activeId}
          admin={admin}
          depth={depth + 1}
          onSelect={onSelect}
          onAddChild={onAddChild}
          onRename={onRename}
          onDelete={onDelete}
          onDropItem={onDropItem}
        />
      )}
    </div>
  );
}
