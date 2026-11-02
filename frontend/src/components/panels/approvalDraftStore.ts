/**
 * ask_human / 审批表单草稿的浏览器持久化：
 * 用户填到一半刷新或关闭页面后，审批重新出现时回填已填内容。
 * 只做 localStorage 读写与类型净化，不感知 React。
 */

import type { FormField } from "../../types";

const KEY_PREFIX = "approvalFormDraft:";
const DRAFT_VERSION = 1;
/** 审批可能长期挂起（interrupt 模式无超时），草稿保留一周后自然过期 */
const DRAFT_TTL_MS = 7 * 24 * 60 * 60 * 1000;

interface StoredApprovalFormDraft {
  version: number;
  savedAt: number;
  values: Record<string, unknown>;
}

function draftKey(approvalId: string): string {
  return `${KEY_PREFIX}${approvalId}`;
}

/**
 * 按字段类型净化已存值；类型不符或选项类字段已不在选项内返回 undefined，
 * 由调用方回退到字段默认值。
 */
function sanitizeDraftValue(field: FormField, value: unknown): unknown {
  switch (field.type) {
    case "text":
    case "textarea":
      return typeof value === "string" ? value : undefined;
    case "number":
      // number 控件清空时以 "" 表示，与 FormFieldRenderer 的取值行为一致
      if (value === "") return "";
      return typeof value === "number" && Number.isFinite(value)
        ? value
        : undefined;
    case "checkbox":
      return typeof value === "boolean" ? value : undefined;
    case "select":
    case "radio":
      return typeof value === "string" &&
        (field.options === undefined || field.options.includes(value))
        ? value
        : undefined;
    case "multi_select":
      return Array.isArray(value) &&
        value.every((item) => typeof item === "string") &&
        (field.options === undefined ||
          value.every((item) => field.options!.includes(item)))
        ? value
        : undefined;
    default:
      return undefined;
  }
}

/** 读取草稿并只保留当前字段仍能承载的值；无可用值时返回 null。 */
export function loadApprovalFormDraft(
  approvalId: string,
  fields: FormField[],
): Record<string, unknown> | null {
  let stored: unknown;
  try {
    stored = JSON.parse(localStorage.getItem(draftKey(approvalId)) || "null");
  } catch {
    return null;
  }
  if (
    !stored ||
    typeof stored !== "object" ||
    (stored as StoredApprovalFormDraft).version !== DRAFT_VERSION ||
    typeof (stored as StoredApprovalFormDraft).savedAt !== "number" ||
    Date.now() - (stored as StoredApprovalFormDraft).savedAt > DRAFT_TTL_MS
  ) {
    return null;
  }
  const values = (stored as StoredApprovalFormDraft).values;
  if (!values || typeof values !== "object") return null;

  const draft: Record<string, unknown> = {};
  let restored = false;
  for (const field of fields) {
    if (!Object.prototype.hasOwnProperty.call(values, field.name)) continue;
    const sanitized = sanitizeDraftValue(field, values[field.name]);
    if (sanitized === undefined) continue;
    draft[field.name] = sanitized;
    restored = true;
  }
  return restored ? draft : null;
}

/** 保存草稿；存储不可用（隐私模式/配额满）时静默降级，不影响提交。 */
export function saveApprovalFormDraft(
  approvalId: string,
  values: Record<string, unknown>,
): void {
  try {
    localStorage.setItem(
      draftKey(approvalId),
      JSON.stringify({ version: DRAFT_VERSION, savedAt: Date.now(), values }),
    );
  } catch {
    /* 草稿是尽力而为的增强，不阻塞表单交互 */
  }
}

/** 审批终态（提交成功/取消/过期）后清除对应草稿。 */
export function removeApprovalFormDraft(approvalId: string): void {
  try {
    localStorage.removeItem(draftKey(approvalId));
  } catch {
    /* 同上 */
  }
}
