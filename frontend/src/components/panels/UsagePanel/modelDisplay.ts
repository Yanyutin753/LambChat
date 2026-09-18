import type { UsageRankingItem } from "../../../types/usage";

/** 只依赖 value/label 两个字段，兼容 SettingsContext 的 AvailableModel */
export interface ModelLabelSource {
  value: string;
  label?: string;
}

export type ModelLabelMap = Map<string, string>;

/** 模型 value（日志里存的 ID）→ 展示名映射；无 label 的条目跳过，交由回退逻辑 */
export function buildModelLabelMap(
  models: readonly ModelLabelSource[] | null | undefined,
): ModelLabelMap {
  const map: ModelLabelMap = new Map();
  for (const model of models ?? []) {
    const value = model.value?.trim();
    const label = model.label?.trim();
    if (!value || !label) continue;
    map.set(value, label);
  }
  return map;
}

/** 优先返回展示名；模型已删除/未配置时回退原始 ID，空值返回空串（由调用方渲染 "-"） */
export function modelDisplayName(
  labels: ModelLabelMap,
  value: string | null | undefined,
): string {
  const raw = value?.trim() ?? "";
  return labels.get(raw) ?? raw;
}

/** 模型用量排行：把聚合返回的模型 ID 换成展示名，未知模型保持原样 */
export function withModelDisplayNames(
  items: readonly UsageRankingItem[],
  labels: ModelLabelMap,
): UsageRankingItem[] {
  return items.map((item) => {
    const name = modelDisplayName(labels, item.id);
    return name && name !== item.id ? { ...item, name } : item;
  });
}
