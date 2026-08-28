import type { TFunction } from "i18next";
import type { AgentOption } from "../../types";

export function resolveThinkingPresentation(
  agentOptions: Record<string, AgentOption> | undefined,
  agentOptionValues: Record<string, boolean | string | number>,
  t: TFunction,
): { label?: string } {
  if (!agentOptions) return {};
  const optionEntry = Object.entries(agentOptions).find(
    ([, opt]) => opt.options && opt.options.length > 0,
  );
  if (!optionEntry) return {};
  const [key, opt] = optionEntry;
  const val = agentOptionValues[key] ?? opt.default;
  const selected = opt.options?.find((item) => item.value === val);
  return {
    label: selected?.label_key
      ? t(selected.label_key)
      : selected?.label || String(val),
  };
}
