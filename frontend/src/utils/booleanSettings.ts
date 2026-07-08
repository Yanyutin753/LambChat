export function parseBooleanSettingValue(value: unknown): boolean {
  if (value === true) return true;
  if (value === false || value === null || value === undefined) return false;
  if (typeof value === "number") return value !== 0;
  if (typeof value !== "string") return false;

  const normalized = value.trim().toLowerCase();
  return ["1", "true", "yes", "on", "enabled"].includes(normalized);
}
