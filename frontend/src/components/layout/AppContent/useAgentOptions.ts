import { useState, useEffect, useCallback, useRef } from "react";
import type { AgentInfo } from "../../../types";

export const DEFAULT_THINKING_LEVEL_STORAGE_KEY = "defaultThinkingLevel";

const THINKING_LEVEL_OPTION_DEFS = [
  { value: "low", label_key: "agentOptions.enableThinking.options.low" },
  { value: "medium", label_key: "agentOptions.enableThinking.options.medium" },
  { value: "high", label_key: "agentOptions.enableThinking.options.high" },
  { value: "max", label_key: "agentOptions.enableThinking.options.max" },
] as const;

const SANDBOX_OPTION_DEFS = [
  { value: "cloud", label_key: "agentOptions.sandbox.options.cloud" },
  { value: "local", label_key: "agentOptions.sandbox.options.local" },
] as const;

/**
 * 注入会话沙箱选项（M3）：所有 agent 统一注入，云端档为既有默认行为；
 * 后端将来自行下发 sandbox 选项时尊重后端定义，不覆盖。
 */
export function injectSandboxOption(
  options: AgentInfo["options"],
): AgentInfo["options"] {
  if (!options || options.sandbox) {
    return options;
  }
  return {
    ...options,
    sandbox: {
      type: "string",
      default: "cloud",
      label: "Sandbox",
      label_key: "agentOptions.sandbox.label",
      description: "Choose where sandboxed commands run",
      description_key: "agentOptions.sandbox.description",
      icon: "Monitor",
      options: [...SANDBOX_OPTION_DEFS],
    },
  };
}

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

  return injectSandboxOption(
    Object.fromEntries(
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
              option.description_key ||
              "agentOptions.enableThinking.description",
            icon: option.icon || "Brain",
            options: option.options?.length
              ? option.options
              : [...THINKING_LEVEL_OPTION_DEFS],
          },
        ];
      }),
    ),
  );
}

/**
 * 默认本地档：daemon 在线时新会话默认选本地，离线默认云端。
 * `localStorage["defaultSandboxMode"]`（"local"|"cloud"）是用户显式偏好，优先于
 * 在线状态推导——偏好云端的高级用户不会被自动翻回本地。
 */
export function resolveSandboxDefault(
  stored: string | null,
  online: boolean,
): "local" | "cloud" {
  if (stored === "local" || stored === "cloud") return stored;
  return online ? "local" : "cloud";
}

/**
 * daemon 离线→在线翻转时，是否应把沙箱档自动切到本地：
 * 仅当本会话未手动切换过（sandboxTouched）、当前不在本地档、且用户没有
 * 显式偏好云端时翻转。
 */
export function shouldAdoptLocalOnOnline(
  currentSandbox: boolean | string | number | undefined,
  sandboxTouched: boolean,
  storedPreference: string | null,
): boolean {
  if (sandboxTouched) return false;
  if (storedPreference === "cloud") return false;
  return currentSandbox !== "local";
}

/** daemon 首次上线（离线→在线翻转）时由沙箱状态层派发，默认本地档跟进。 */
export const SANDBOX_ONLINE_CHANGED_EVENT = "sandbox-online-changed";

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

export interface SandboxDefaultHints {
  /** daemon 是否在线（多机任一在线即在线）；缺省按离线处理（云端默认，向后兼容） */
  sandboxOnline?: boolean;
}

function applySandboxDefault(
  defaultValues: Record<string, boolean | string | number>,
  storage: StorageLike | undefined,
  hints?: SandboxDefaultHints,
): Record<string, boolean | string | number> {
  if (!("sandbox" in defaultValues)) {
    return defaultValues;
  }
  const stored =
    storage?.getItem("defaultSandboxMode") ??
    (typeof window !== "undefined"
      ? window.localStorage.getItem("defaultSandboxMode")
      : null);
  return {
    ...defaultValues,
    sandbox: resolveSandboxDefault(stored, hints?.sandboxOnline ?? false),
  };
}

export function buildAgentOptionValues(
  options?: AgentInfo["options"],
  restoredOptions?: Record<string, boolean | string | number>,
  storage: StorageLike | undefined = typeof window !== "undefined"
    ? window.localStorage
    : undefined,
  hints?: SandboxDefaultHints,
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

  defaultValues = applySandboxDefault(defaultValues, storage, hints);

  if (!restoredOptions) {
    return defaultValues;
  }

  return {
    ...defaultValues,
    ...normalizeAgentOptionValues(restoredOptions),
  };
}

export type AgentOptionSyncMode = "restore" | "reset" | "preserve" | "skip";

export function getAgentOptionSyncMode({
  currentAgentId,
  previousAgentId,
  optionsJson,
  previousOptionsJson,
  hasPendingRestoredOptions,
}: {
  currentAgentId: string;
  previousAgentId?: string;
  optionsJson: string;
  previousOptionsJson: string;
  hasPendingRestoredOptions: boolean;
}): AgentOptionSyncMode {
  if (hasPendingRestoredOptions) {
    return "restore";
  }

  if (!previousAgentId || previousAgentId !== currentAgentId) {
    return "reset";
  }

  if (optionsJson === previousOptionsJson) {
    return "skip";
  }

  return "preserve";
}

export function useAgentOptions(agents: AgentInfo[], currentAgent: string) {
  const [agentOptionValues, setAgentOptionValues] = useState<
    Record<string, boolean | string | number>
  >({});
  const pendingRestoredOptionsRef = useRef<Record<
    string,
    boolean | string | number
  > | null>(null);
  // Track serialized agent options to avoid rebuilding on every agents ref change
  const prevAgentOptionsJsonRef = useRef<string>("");
  const prevAgentIdRef = useRef<string | undefined>(undefined);

  const currentAgentInfo = agents.find((a) => a.id === currentAgent);
  const currentAgentOptions =
    normalizeAgentOptions(currentAgentInfo?.options) || {};

  useEffect(() => {
    const options = normalizeAgentOptions(
      agents.find((a) => a.id === currentAgent)?.options,
    );
    const optionsJson = JSON.stringify(options);
    const syncMode = getAgentOptionSyncMode({
      currentAgentId: currentAgent,
      previousAgentId: prevAgentIdRef.current,
      optionsJson,
      previousOptionsJson: prevAgentOptionsJsonRef.current,
      hasPendingRestoredOptions: pendingRestoredOptionsRef.current !== null,
    });

    prevAgentIdRef.current = currentAgent;
    const prevJson = prevAgentOptionsJsonRef.current;
    prevAgentOptionsJsonRef.current = optionsJson;

    if (syncMode === "skip") {
      return;
    }

    if (syncMode === "restore" && pendingRestoredOptionsRef.current) {
      const nextValues = buildAgentOptionValues(
        options,
        pendingRestoredOptionsRef.current,
      );
      pendingRestoredOptionsRef.current = null;
      setAgentOptionValues(nextValues);
      return;
    }

    if (syncMode === "reset" || !prevJson) {
      setAgentOptionValues(buildAgentOptionValues(options));
      return;
    }

    setAgentOptionValues((prev) => {
      const rebuilt = buildAgentOptionValues(options);
      for (const key of Object.keys(prev)) {
        if (
          key in rebuilt ||
          key === "sandbox_workspace" ||
          key === "sandbox_machine_id"
        ) {
          (rebuilt as Record<string, boolean | string | number>)[key] =
            prev[key];
        }
      }
      return rebuilt;
    });
  }, [currentAgent, agents]);

  useEffect(() => {
    const handleThinkingPreferenceUpdated = () => {
      const options = normalizeAgentOptions(
        agents.find((a) => a.id === currentAgent)?.options,
      );
      // Only update the thinking level default; preserve all other user selections.
      setAgentOptionValues((prev) => ({
        ...buildAgentOptionValues(options),
        // Keep non-thinking user selections intact
        ...Object.fromEntries(
          Object.entries(prev).filter(([k]) => k !== "enable_thinking"),
        ),
      }));
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

  // 默认本地档：daemon 离线→在线首次翻转时，若用户本会话未手动切换过沙箱档
  // 且没有显式偏好云端，自动切到本地（镜像 thinking-preference-updated 模式）
  const sandboxTouchedRef = useRef(false);
  useEffect(() => {
    const handleSandboxOnline = () => {
      setAgentOptionValues((prev) => {
        if (
          !shouldAdoptLocalOnOnline(
            prev.sandbox,
            sandboxTouchedRef.current,
            typeof window !== "undefined"
              ? window.localStorage.getItem("defaultSandboxMode")
              : null,
          )
        ) {
          return prev;
        }
        return { ...prev, sandbox: "local" };
      });
    };

    window.addEventListener(SANDBOX_ONLINE_CHANGED_EVENT, handleSandboxOnline);
    return () => {
      window.removeEventListener(
        SANDBOX_ONLINE_CHANGED_EVENT,
        handleSandboxOnline,
      );
    };
  }, []);

  const handleToggleAgentOption = useCallback(
    (key: string, value: boolean | string | number) => {
      if (key === "sandbox") {
        sandboxTouchedRef.current = true;
      }
      setAgentOptionValues((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  // Reset to agent defaults (for new session)
  const resetAgentOptionDefaults = useCallback(() => {
    const options = normalizeAgentOptions(
      agents.find((a) => a.id === currentAgent)?.options,
    );
    setAgentOptionValues(buildAgentOptionValues(options));
  }, [agents, currentAgent]);

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
    resetAgentOptionDefaults,
  };
}
