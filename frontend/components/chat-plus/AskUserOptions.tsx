"use client";

import { useState } from "react";
import type { AskUserPayload } from "@/lib/askUser";

interface Props {
  payload: AskUserPayload;
  onPick: (text: string) => void;
  disabled: boolean;
}

// 渲染模型的 ask-user 提问：选项按钮 + 始终附带的「其他」自由输入框。
// 单选：点选项即发送；多选：勾选多项 + 补充文本后统一提交。
export default function AskUserOptions({ payload, onPick, disabled }: Props) {
  const multi = payload.multiSelect === true;
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [other, setOther] = useState("");

  function toggle(label: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  }

  // 单选：直接发送该选项
  function pickSingle(label: string) {
    if (disabled) return;
    onPick(label);
  }

  // 单选下的「其他」框发送
  function sendOther() {
    const text = other.trim();
    if (!text || disabled) return;
    onPick(text);
    setOther("");
  }

  // 多选：合并勾选项 + 补充文本，统一提交
  function submitMulti() {
    if (disabled) return;
    const parts = payload.options
      .filter((o) => checked.has(o.label))
      .map((o) => o.label);
    const extra = other.trim();
    if (extra) parts.push(extra);
    if (parts.length === 0) return;
    onPick(parts.join("、"));
    setChecked(new Set());
    setOther("");
  }

  const multiCanSubmit = checked.size > 0 || other.trim().length > 0;

  return (
    <div className="ml-11 mt-2 w-full max-w-md">
      <p className="mb-2 text-sm font-medium text-gray-700">{payload.question}</p>
      <div className="flex flex-col gap-2">
        {payload.options.map((o) =>
          multi ? (
            <label
              key={o.label}
              className={`flex cursor-pointer items-start gap-2 rounded-lg border px-4 py-2.5 text-left text-sm transition-colors shadow-sm ${
                checked.has(o.label)
                  ? "border-purple-400 bg-purple-50 text-purple-700"
                  : "border-gray-200 bg-white text-gray-700 hover:border-purple-300 hover:bg-purple-50"
              } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
            >
              <input
                type="checkbox"
                className="mt-0.5"
                checked={checked.has(o.label)}
                disabled={disabled}
                onChange={() => toggle(o.label)}
              />
              <span>
                <span className="font-medium">{o.label}</span>
                {o.description && (
                  <span className="block text-xs text-gray-400">{o.description}</span>
                )}
              </span>
            </label>
          ) : (
            <button
              key={o.label}
              type="button"
              disabled={disabled}
              onClick={() => pickSingle(o.label)}
              className="rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-left text-sm text-gray-700 hover:border-purple-300 hover:bg-purple-50 hover:text-purple-700 transition-colors shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="font-medium">{o.label}</span>
              {o.description && (
                <span className="block text-xs text-gray-400">{o.description}</span>
              )}
            </button>
          )
        )}

        {/* 始终附带的「其他」自由输入框 */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={other}
            disabled={disabled}
            onChange={(e) => setOther(e.target.value)}
            onKeyDown={(e) => {
              if (!multi && e.key === "Enter") {
                e.preventDefault();
                sendOther();
              }
            }}
            placeholder="其他（自行补充）…"
            className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 outline-none focus:border-purple-400 disabled:opacity-60"
          />
          {!multi && (
            <button
              type="button"
              disabled={disabled || !other.trim()}
              onClick={sendOther}
              className="shrink-0 rounded-lg bg-purple-600 px-3 py-2 text-sm text-white hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              发送
            </button>
          )}
        </div>

        {/* 多选：统一提交按钮 */}
        {multi && (
          <button
            type="button"
            disabled={disabled || !multiCanSubmit}
            onClick={submitMulti}
            className="mt-1 self-start rounded-lg bg-purple-600 px-4 py-2 text-sm text-white hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            提交
          </button>
        )}
      </div>
    </div>
  );
}
