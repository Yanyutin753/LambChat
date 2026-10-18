/** Persistent goal mutations and background status reconciliation. */
import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { sessionApi, type BackendSession } from "../../services/api";
import type { MessageAttachment } from "../../types";
import type { ChatSubmissionCallbacks, UseAgentOptions } from "./types";
import type { FrontendGoalCommand } from "./goalCommands";
import { resolveRunEnabledSkills } from "./runSkillOverrides";
import {
  notifySubmissionAccepted,
  notifySubmissionRejected,
} from "./submissionNotifications";
import type { PersistentGoal } from "../../services/api/session";
import i18n from "../../i18n";
import { translateApiError } from "../../utils/backendErrors";
import { selectPersistentGoal } from "./persistentGoalState";

interface PersistentGoalRuntimeDeps {
  sessionId: string | null;
  persistentGoal: PersistentGoal | null;
  setPersistentGoalState: Dispatch<SetStateAction<PersistentGoal | null>>;
  setPersistentGoalBusy: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  sessionIdRef: RefObject<string | null>;
  currentRunIdRef: RefObject<string | null>;
  isSendingRef: RefObject<boolean>;
  isLoadingHistoryRef: RefObject<boolean>;
  loadHistoryRef: RefObject<
    ((sessionId: string, runId?: string) => Promise<unknown>) | null
  >;
}

export function usePersistentGoalRuntime({
  sessionId,
  persistentGoal,
  setPersistentGoalState,
  setPersistentGoalBusy,
  setError,
  sessionIdRef,
  currentRunIdRef,
  isSendingRef,
  isLoadingHistoryRef,
  loadHistoryRef,
}: PersistentGoalRuntimeDeps) {
  const persistentGoalRef = useRef<PersistentGoal | null>(null);
  const persistentMutationEpochRef = useRef(0);
  const setPersistentGoal = useCallback(
    (updater: SetStateAction<PersistentGoal | null>) => {
      const next =
        typeof updater === "function"
          ? updater(persistentGoalRef.current)
          : updater;
      persistentGoalRef.current = next;
      setPersistentGoalState(next);
    },
    [setPersistentGoalState],
  );
  const persistentMutationRef = useRef(false);
  const controlPersistentGoal = useCallback(
    async (action: "pause" | "resume" | "clear") => {
      const target = sessionIdRef.current;
      if (!target || persistentMutationRef.current) return;
      persistentMutationRef.current = true;
      persistentMutationEpochRef.current += 1;
      setPersistentGoalBusy(true);
      try {
        const response = await sessionApi.controlPersistentGoal(target, action);
        if (sessionIdRef.current !== target) return;
        if (response.goal && response.goal.session_id !== target)
          throw new Error(i18n.t("chat.goalPersistent.noGoal"));
        setPersistentGoal((previous) =>
          selectPersistentGoal(previous, response.goal, target),
        );
        setError(null);
      } catch (error) {
        if (sessionIdRef.current === target) {
          const apiError = error as Error & {
            code?: string;
            args?: Record<string, unknown>;
          };
          setError(
            translateApiError(
              apiError.code,
              apiError.message,
              apiError.args,
              i18n.t,
            ),
          );
        }
      } finally {
        persistentMutationRef.current = false;
        setPersistentGoalBusy(false);
      }
    },
    [sessionIdRef, setError, setPersistentGoal, setPersistentGoalBusy],
  );

  const updatePersistentGoal = useCallback(
    async (
      objective: string,
      rubric: string,
      expectedRevision: number,
    ): Promise<boolean> => {
      const target = sessionIdRef.current;
      if (!target || persistentMutationRef.current) return false;
      persistentMutationRef.current = true;
      persistentMutationEpochRef.current += 1;
      setPersistentGoalBusy(true);
      try {
        const response = await sessionApi.updatePersistentGoal(target, {
          objective,
          rubric,
          expected_revision: expectedRevision,
        });
        if (sessionIdRef.current !== target) return false;
        if (response.goal.session_id !== target)
          throw new Error(i18n.t("chat.goalPersistent.noGoal"));
        setPersistentGoal((previous) =>
          selectPersistentGoal(previous, response.goal, target),
        );
        setError(null);
        return true;
      } catch (error) {
        if (sessionIdRef.current === target) {
          const apiError = error as Error & {
            code?: string;
            args?: Record<string, unknown>;
          };
          setError(
            translateApiError(
              apiError.code,
              apiError.message,
              apiError.args,
              i18n.t,
            ),
          );
        }
        return false;
      } finally {
        persistentMutationRef.current = false;
        setPersistentGoalBusy(false);
      }
    },
    [sessionIdRef, setPersistentGoal, setPersistentGoalBusy, setError],
  );

  const persistentGoalId = persistentGoal?.id;
  const persistentGoalStatus = persistentGoal?.status;
  const pendingUsageSettlement =
    persistentGoal?.run_accounting?.at(-1)?.completed === false;
  useEffect(() => {
    if (
      !sessionId ||
      !persistentGoalId ||
      !persistentGoalStatus ||
      (!["active", "waiting_human"].includes(persistentGoalStatus) &&
        !(persistentGoalStatus === "paused" && pendingUsageSettlement))
    )
      return;
    let cancelled = false;
    let inFlight = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      clearTimeout(timer);
      if (!cancelled)
        timer = setTimeout(
          () => void refresh(),
          Math.min(3000 * 2 ** failures, 60000),
        );
    };
    const refresh = async () => {
      if (cancelled || document.visibilityState === "hidden") return;
      if (inFlight) return;
      if (
        persistentMutationRef.current ||
        isSendingRef.current ||
        isLoadingHistoryRef.current
      ) {
        schedule();
        return;
      }
      inFlight = true;
      const mutationEpoch = persistentMutationEpochRef.current;
      try {
        const response = await sessionApi.getPersistentGoal(sessionId);
        failures = 0;
        if (
          cancelled ||
          sessionIdRef.current !== sessionId ||
          mutationEpoch !== persistentMutationEpochRef.current ||
          isSendingRef.current ||
          isLoadingHistoryRef.current
        )
          return;
        const previous = persistentGoalRef.current;
        const selected = selectPersistentGoal(
          previous,
          response.goal,
          sessionId,
        );
        if (selected !== response.goal) return;
        setPersistentGoal(selected);
        if (
          response.goal &&
          ((response.goal.current_run_id &&
            response.goal.current_run_id !== currentRunIdRef.current) ||
            response.goal.accounting.turns > (previous?.accounting.turns ?? 0))
        ) {
          // A run target only opens historical content; session reconciliation also attaches SSE.
          await loadHistoryRef.current?.(sessionId);
        }
      } catch (error) {
        failures = Math.min(failures + 1, 5);
        if (!cancelled && failures === 1)
          console.warn("[Goal] Failed to refresh persistent goal", error);
      } finally {
        inFlight = false;
        schedule();
      }
    };
    const resume = () => {
      clearTimeout(timer);
      if (document.visibilityState !== "hidden") {
        failures = 0;
        void refresh();
      }
    };
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("online", resume);
    void refresh();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("online", resume);
    };
  }, [
    sessionId,
    persistentGoalId,
    persistentGoalStatus,
    pendingUsageSettlement,
    setPersistentGoal,
    sessionIdRef,
    currentRunIdRef,
    isSendingRef,
    isLoadingHistoryRef,
    loadHistoryRef,
  ]);

  return {
    setPersistentGoal,
    persistentMutationRef,
    persistentMutationEpochRef,
    controlPersistentGoal,
    updatePersistentGoal,
  };
}

interface PersistentGoalCommandDeps {
  command: Extract<
    FrontendGoalCommand,
    { action: "persist" | "pause" | "resume" | "clear" }
  >;
  attachments?: MessageAttachment[];
  submissionCallbacks?: ChatSubmissionCallbacks;
  persistentMutationRef: RefObject<boolean>;
  submitInFlightRef: RefObject<boolean>;
  persistentMutationEpochRef: RefObject<number>;
  setPersistentGoalBusy: Dispatch<SetStateAction<boolean>>;
  sessionIdRef: RefObject<string | null>;
  streamVersionRef: RefObject<number>;
  currentAgent: string;
  autoModeEnabled: boolean;
  options?: UseAgentOptions;
  agentOptions?: Record<string, boolean | string | number>;
  selectedTeamId: string | null;
  pendingProjectIdRef: RefObject<string | null>;
  setSessionId: Dispatch<SetStateAction<string | null>>;
  setNewlyCreatedSession: Dispatch<SetStateAction<BackendSession | null>>;
  setCurrentProjectId: Dispatch<SetStateAction<string | null>>;
  bindSteerSession: (sessionId: string) => void;
  persistentGoal: PersistentGoal | null;
  setPersistentGoal: Dispatch<SetStateAction<PersistentGoal | null>>;
  setGoalModeEnabled: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  runEnabledSkills?: string[];
}

export async function submitPersistentGoalCommand({
  command,
  attachments,
  submissionCallbacks,
  persistentMutationRef,
  submitInFlightRef,
  persistentMutationEpochRef,
  setPersistentGoalBusy,
  sessionIdRef,
  streamVersionRef,
  currentAgent,
  autoModeEnabled,
  options,
  agentOptions,
  selectedTeamId,
  pendingProjectIdRef,
  setSessionId,
  setNewlyCreatedSession,
  setCurrentProjectId,
  bindSteerSession,
  persistentGoal,
  setPersistentGoal,
  setGoalModeEnabled,
  setError,
  runEnabledSkills,
}: PersistentGoalCommandDeps): Promise<void> {
  if (attachments?.length) {
    setError(i18n.t("chat.goalPersistent.attachmentsUnsupported"));
    notifySubmissionRejected(submissionCallbacks);
    return;
  }
  if (persistentMutationRef.current || submitInFlightRef.current) {
    notifySubmissionRejected(submissionCallbacks);
    return;
  }
  persistentMutationRef.current = true;
  persistentMutationEpochRef.current += 1;
  setPersistentGoalBusy(true);
  const originSession = sessionIdRef.current;
  const originStreamVersion = streamVersionRef.current;
  let target = originSession;
  try {
    if (command.action !== "persist" && !target)
      throw new Error(i18n.t("chat.goalPersistent.noGoal"));
    if (!target) {
      const created = await sessionApi.create({
        name: command.action === "persist" ? command.goal.objective : undefined,
        metadata: {
          agent_id: currentAgent,
          auto_mode: autoModeEnabled,
          agent_options: {
            ...options?.getAgentOptions?.(),
            ...agentOptions,
          },
          team_id: currentAgent === "team" ? selectedTeamId : null,
          persona_preset_id: options?.getPersonaPresetId?.() || null,
          disabled_skills: options?.getDisabledSkills?.() || [],
          enabled_skills: resolveRunEnabledSkills({
            personaPresetId: options?.getPersonaPresetId?.() || null,
            personaEnabledSkills: options?.getEnabledSkills?.(),
            runEnabledSkills,
          }),
          disabled_mcp_tools: options?.getDisabledMcpTools?.() || [],
          project_id: pendingProjectIdRef.current,
        },
      });
      if (
        sessionIdRef.current !== originSession ||
        streamVersionRef.current !== originStreamVersion
      ) {
        notifySubmissionRejected(submissionCallbacks);
        return;
      }
      target = created.id;
      sessionIdRef.current = target;
      setSessionId(target);
      setNewlyCreatedSession(created);
      setCurrentProjectId(pendingProjectIdRef.current);
      bindSteerSession(target);
    }
    const response =
      command.action === "persist"
        ? await sessionApi.putPersistentGoal(target, {
            objective: command.goal.objective,
            rubric: command.goal.rubric!,
            ...(persistentGoal
              ? { expected_revision: persistentGoal.revision }
              : {}),
          })
        : await sessionApi.controlPersistentGoal(target, command.action);
    if (
      sessionIdRef.current !== target ||
      streamVersionRef.current !== originStreamVersion
    ) {
      notifySubmissionRejected(submissionCallbacks);
      return;
    }
    if (command.action === "persist" && !response.goal)
      throw new Error(i18n.t("chat.goalPersistent.noGoal"));
    if (response.goal && response.goal.session_id !== target)
      throw new Error(i18n.t("chat.goalPersistent.noGoal"));
    setPersistentGoal((previous) =>
      selectPersistentGoal(previous, response.goal, target),
    );
    setGoalModeEnabled(false);
    setError(null);
    notifySubmissionAccepted(submissionCallbacks);
  } catch (error) {
    const apiError = error as Error & {
      code?: string;
      args?: Record<string, unknown>;
    };
    if (
      sessionIdRef.current === target &&
      streamVersionRef.current === originStreamVersion
    )
      setError(
        translateApiError(
          apiError.code,
          apiError.message,
          apiError.args,
          i18n.t,
        ),
      );
    notifySubmissionRejected(submissionCallbacks);
  } finally {
    persistentMutationRef.current = false;
    setPersistentGoalBusy(false);
  }
}
