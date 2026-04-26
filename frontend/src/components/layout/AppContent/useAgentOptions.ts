import { useState, useEffect, useCallback, useRef } from "react";
import type { AgentInfo } from "../../../types";

export const DEFAULT_THINKING_LEVEL_STORAGE_KEY = "defaultThinkingLevel";

const THINKING_LEVEL_OPTION_DEFS = [
  { value: "off", label_key: "agentOptions.enableThinking.options.off" },
  { value: "low", label_key: "agentOptions.enableThinking.options.low" },
  { value: "medium", label_key: "agentOptions.enableThinking.options.medium" },
  { value: "high", label_key: "agentOptions.enableThinking.options.high" },
  { value: "max", label_key: "agentOptions.enableThinking.options.max" },
] as const;

function normalizeThinkingOptionValue(value: boolean | string | number) {
  if (value === true) return "medium";
  if (value === false) return "off";
  if (typeof value !== "string") return value;

  const normalized = value.trim().toLowerCase();
  if (["off", "low", "medium", "high", "max"].includes(normalized)) {
    return normalized;
  }
  if (["enabled", "enable", "on", "true"].includes(normalized)) {
    return "medium";
  }
  if (["disabled", "disable", "false", "none"].includes(normalized)) {
    return "off";
  }
  return value;
}

export function normalizeAgentOptionValues(
  values?: Record<string, boolean | string | number>,
): Record<string, boolean | string | number> | undefined {
  if (!values) return values;

  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => {
      if (key === "enable_thinking") {
        return [key, normalizeThinkingOptionValue(value)];
      }
      return [key, value];
    }),
  );
}

export function normalizeAgentOptions(
  options?: AgentInfo["options"],
): AgentInfo["options"] | undefined {
  if (!options) return options;

  return Object.fromEntries(
    Object.entries(options).map(([key, option]) => {
      if (key !== "enable_thinking") {
        return [key, option];
      }

      return [
        key,
        {
          ...option,
          type: "string",
          default: normalizeThinkingOptionValue(option.default),
          label: option.label || "Thinking",
          label_key: option.label_key || "agentOptions.enableThinking.label",
          description:
            option.description ||
            "Control thinking intensity (supported models only)",
          description_key:
            option.description_key || "agentOptions.enableThinking.description",
          icon: option.icon || "Brain",
          options: option.options?.length
            ? option.options
            : [...THINKING_LEVEL_OPTION_DEFS],
        },
      ];
    }),
  );
}

type StorageLike = Pick<Storage, "getItem">;

function applyStoredAgentOptionDefaults(
  defaultValues: Record<string, boolean | string | number>,
  options?: AgentInfo["options"],
  storage?: StorageLike,
): Record<string, boolean | string | number> {
  if (!options?.enable_thinking) {
    return defaultValues;
  }

  const storedThinkingLevel = storage?.getItem(
    DEFAULT_THINKING_LEVEL_STORAGE_KEY,
  );
  if (!storedThinkingLevel) {
    return defaultValues;
  }

  return {
    ...defaultValues,
    enable_thinking: normalizeThinkingOptionValue(storedThinkingLevel),
  };
}

export function buildAgentOptionValues(
  options?: AgentInfo["options"],
  restoredOptions?: Record<string, boolean | string | number>,
  storage: StorageLike | undefined = typeof window !== "undefined"
    ? window.localStorage
    : undefined,
): Record<string, boolean | string | number> {
  const normalizedOptions = normalizeAgentOptions(options);
  let defaultValues: Record<string, boolean | string | number> = {};

  if (normalizedOptions) {
    Object.entries(normalizedOptions).forEach(([key, option]) => {
      defaultValues[key] = option.default;
    });
  }

  defaultValues = applyStoredAgentOptionDefaults(
    defaultValues,
    normalizedOptions,
    storage,
  );

  if (!restoredOptions) {
    return defaultValues;
  }

  return {
    ...defaultValues,
    ...normalizeAgentOptionValues(restoredOptions),
  };
}

export function useAgentOptions(agents: AgentInfo[], currentAgent: string) {
  const [agentOptionValues, setAgentOptionValues] = useState<
    Record<string, boolean | string | number>
  >({});
  const pendingRestoredOptionsRef = useRef<Record<
    string,
    boolean | string | number
  > | null>(null);

  const currentAgentInfo = agents.find((a) => a.id === currentAgent);
  const currentAgentOptions =
    normalizeAgentOptions(currentAgentInfo?.options) || {};

  // Preserve user-chosen option values when agents data refreshes
  // (e.g., tab visibility change triggers fetchAgents). Only override with
  // defaults for keys the user hasn't explicitly changed.
  const userOverridesRef = useRef<Record<string, boolean | string | number>>({});

  useEffect(() => {
    const options = normalizeAgentOptions(
      agents.find((a) => a.id === currentAgent)?.options,
    );
    const restored = pendingRestoredOptionsRef.current;
    const nextValues = buildAgentOptionValues(
      options,
      restored || undefined,
    );

    pendingRestoredOptionsRef.current = null;

    if (restored) {
      // Full restore from session metadata — reset overrides
      userOverridesRef.current = { ...nextValues };
      setAgentOptionValues(nextValues);
    } else {
      // Agents refreshed — keep user overrides, only add new defaults
      setAgentOptionValues((prev) => {
        const merged = { ...nextValues, ...prev, ...userOverridesRef.current };
        userOverridesRef.current = merged;
        return merged;
      });
    }
  }, [currentAgent, agents]);

  useEffect(() => {
    const handleThinkingPreferenceUpdated = () => {
      const options = normalizeAgentOptions(
        agents.find((a) => a.id === currentAgent)?.options,
      );
      setAgentOptionValues(buildAgentOptionValues(options));
    };

    window.addEventListener(
      "thinking-preference-updated",
      handleThinkingPreferenceUpdated,
    );
    return () => {
      window.removeEventListener(
        "thinking-preference-updated",
        handleThinkingPreferenceUpdated,
      );
    };
  }, [agents, currentAgent]);

  const handleToggleAgentOption = useCallback(
    (key: string, value: boolean | string | number) => {
      userOverridesRef.current[key] = value;
      setAgentOptionValues((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  // 从外部恢复配置
  const restoreAgentOptions = useCallback(
    (options: Record<string, boolean | string | number>) => {
      const normalizedOptions = normalizeAgentOptionValues(options) || {};
      pendingRestoredOptionsRef.current = normalizedOptions;
      setAgentOptionValues(normalizedOptions);
    },
    [],
  );

  return {
    agentOptionValues,
    currentAgentOptions,
    handleToggleAgentOption,
    restoreAgentOptions,
  };
}
