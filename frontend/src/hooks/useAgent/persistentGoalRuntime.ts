/** Persistent goal mutations and background status reconciliation. */
import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { sessionApi } from "../../services/api";
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

  const persistentGoalId = persistentGoal?.id;
  const persistentGoalStatus = persistentGoal?.status;
  useEffect(() => {
    if (
      !sessionId ||
      !persistentGoalId ||
      !persistentGoalStatus ||
      !["active", "waiting_human"].includes(persistentGoalStatus)
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
          mutationEpoch !== persistentMutationEpochRef.current
        )
          return;
        const selected = selectPersistentGoal(
          persistentGoalRef.current,
          response.goal,
          sessionId,
        );
        if (selected !== response.goal) return;
        setPersistentGoal(selected);
        if (
          response.goal?.current_run_id &&
          response.goal.current_run_id !== currentRunIdRef.current
        ) {
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
  };
}
