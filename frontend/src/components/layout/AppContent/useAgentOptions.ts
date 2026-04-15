import { useState, useEffect, useCallback, useRef } from "react";
import type { AgentInfo } from "../../../types";

export function buildAgentOptionValues(
  options?: AgentInfo["options"],
  restoredOptions?: Record<string, boolean | string | number>,
): Record<string, boolean | string | number> {
  const defaultValues: Record<string, boolean | string | number> = {};

  if (options) {
    Object.entries(options).forEach(([key, option]) => {
      defaultValues[key] = option.default;
    });
  }

  if (!restoredOptions) {
    return defaultValues;
  }

  return {
    ...defaultValues,
    ...restoredOptions,
  };
}

export function useAgentOptions(agents: AgentInfo[], currentAgent: string) {
  const [agentOptionValues, setAgentOptionValues] = useState<
    Record<string, boolean | string | number>
  >({});
  const pendingRestoredOptionsRef = useRef<
    Record<string, boolean | string | number> | null
  >(null);

  const currentAgentInfo = agents.find((a) => a.id === currentAgent);
  const currentAgentOptions = currentAgentInfo?.options || {};

  useEffect(() => {
    const options = agents.find((a) => a.id === currentAgent)?.options;
    const nextValues = buildAgentOptionValues(
      options,
      pendingRestoredOptionsRef.current || undefined,
    );

    pendingRestoredOptionsRef.current = null;
    setAgentOptionValues(nextValues);
  }, [currentAgent, agents]);

  const handleToggleAgentOption = useCallback(
    (key: string, value: boolean | string | number) => {
      setAgentOptionValues((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  // 从外部恢复配置
  const restoreAgentOptions = useCallback(
    (options: Record<string, boolean | string | number>) => {
      pendingRestoredOptionsRef.current = options;
      setAgentOptionValues(options);
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
