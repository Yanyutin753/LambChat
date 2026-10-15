export const DEFAULT_THINKING_LEVEL_STORAGE_KEY = "defaultThinkingLevel";

/** 归一思考档位值："off" 时代已下线，历史 off 值统一降级到 low */ export function normalizeThinkingOptionValue(
  value: boolean | string | number,
) {
  if (value === true) return "medium";
  if (value === false) return "low";
  if (typeof value !== "string") return value;

  const normalized = value.trim().toLowerCase();
  if (["low", "medium", "high", "max"].includes(normalized)) {
    return normalized;
  }
  if (["enabled", "enable", "on", "true"].includes(normalized)) {
    return "medium";
  }
  if (["off", "disabled", "disable", "none"].includes(normalized)) {
    return "low";
  }
  return value;
}

