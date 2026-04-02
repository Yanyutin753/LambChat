import { useState, useEffect, useCallback } from "react";
import type { AgentInfo } from "../../../types";

export function useAgentOptions(agents: AgentInfo[], currentAgent: string) {
  const [agentOptionValues, setAgentOptionValues] = useState<
    Record<string, boolean | string | number>
  >({});

  const currentAgentInfo = agents.find((a) => a.id === currentAgent);
  const currentAgentOptions = currentAgentInfo?.options || {};

  useEffect(() => {
    const options = agents.find((a) => a.id === currentAgent)?.options;
    if (options) {
      const defaultValues: Record<string, boolean | string | number> = {};
      Object.entries(options).forEach(([key, option]) => {
        defaultValues[key] = option.default;
      });
      setAgentOptionValues(defaultValues);
    } else {
      setAgentOptionValues({});
    }
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
