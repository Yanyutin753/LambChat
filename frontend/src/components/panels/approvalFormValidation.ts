/**
 * ApprovalPanel / ask_human 分步表单的取值与校验纯函数。
 */

import type { FormField } from "../../types";

export function isFieldValueFilled(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim() !== "";
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

/** 所有 required 字段都必须有值（跨步骤提交前使用）。 */
export function isFormFieldsValid(
  fields: FormField[],
  values: Record<string, unknown>,
): boolean {
  return fields.every(
    (field) => !field.required || isFieldValueFilled(values[field.name]),
  );
}

/** multi_select 点选行为：已选则移除，未选则追加。 */
export function toggleMultiSelectValue(
  current: unknown,
  option: string,
): string[] {
  const list = Array.isArray(current) ? current.filter((v) => typeof v === "string") : [];
  return list.includes(option)
    ? list.filter((v) => v !== option)
    : [...list, option];
}
