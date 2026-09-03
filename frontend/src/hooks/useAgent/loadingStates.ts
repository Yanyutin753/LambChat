/** 运行态/加载态状态簇（从 useAgent.ts 下沉，保持主 hook 在 1000 行红线内）。 */
import { useState } from "react";
import type { BackendSession } from "../../services/api";
import type { ConnectionStatus } from "../../types";
import type { ActiveGoalSpec } from "./types";

export function useChatRuntimeStates() {
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyLoadGeneration, setHistoryLoadGeneration] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [newlyCreatedSession, setNewlyCreatedSession] =
    useState<BackendSession | null>(null);
  const [isInitializingSandbox, setIsInitializingSandbox] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [activeGoal, setActiveGoal] = useState<ActiveGoalSpec | null>(null);
  const [goalsByRunId, setGoalsByRunId] = useState<
    Record<string, ActiveGoalSpec>
  >({});
  const [goalModeEnabled, setGoalModeEnabled] = useState(false);

  return {
    isLoading,
    setIsLoading,
    isLoadingHistory,
    setIsLoadingHistory,
    historyLoadGeneration,
    setHistoryLoadGeneration,
    sessionId,
    setSessionId,
    currentProjectId,
    setCurrentProjectId,
    error,
    setError,
    connectionStatus,
    setConnectionStatus,
    currentRunId,
    setCurrentRunId,
    newlyCreatedSession,
    setNewlyCreatedSession,
    isInitializingSandbox,
    setIsInitializingSandbox,
    sandboxError,
    setSandboxError,
    selectedTeamId,
    setSelectedTeamId,
    activeGoal,
    setActiveGoal,
    goalsByRunId,
    setGoalsByRunId,
    goalModeEnabled,
    setGoalModeEnabled,
  };
}
