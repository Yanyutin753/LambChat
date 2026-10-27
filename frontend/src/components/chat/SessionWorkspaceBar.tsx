import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import { InteractiveIcon } from "../common/InteractiveIcon";
import { LoadingSpinner } from "../common/LoadingSpinner";
import {
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from "react";
import { Select } from "../common/ui";
import { sessionApi } from "../../services/api/session";
import { Folder, History } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { useSandboxStatus } from "../../hooks/useSandboxStatus";
import { useAuth } from "../../hooks/useAuth";
import { rememberLocalWorkspace } from "./localWorkspacePreference";
import {
  invokeInShell,
  isShellAvailable,
} from "../../services/tauri/sandboxShell";
import {
  isCurrentWorkspaceMachine,
  parseWorkspaceSelection,
  WORKSPACE_OPTION,
  type WorkspaceSelection,
} from "./workspaceSelection";

interface Props {
  host?: HTMLElement | null;
  ref?: Ref<SessionWorkspaceBarHandle>;
  values: Record<string, boolean | string | number>;
  onChange?: (key: string, value: string) => void;
  disabled: boolean;
  compact?: boolean;
  sessionId?: string | null;
}

export interface SessionWorkspaceBarHandle {
  prepareSubmit: () => boolean;
}

/** A session-level directory entry; the native picker creates a local binding. */
export function SessionWorkspaceBar({
  host,
  ref,
  values,
  onChange,
  disabled,
  compact = false,
  sessionId,
}: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { machines, currentMachineId, defaultMachineId } = useSandboxStatus();
  const [busy, setBusy] = useState(false);
  const picking = useRef(false);
  const onlineMachines = machines.filter((item) => item.online);
  const selectedId = String(
    values.sandbox_machine_id ||
      defaultMachineId ||
      (onlineMachines.length === 1
        ? onlineMachines[0].machine_id
        : machines.length === 1
          ? machines[0].machine_id
          : ""),
  );
  const machine = machines.find((item) => item.machine_id === selectedId);
  const selection = parseWorkspaceSelection(values[WORKSPACE_OPTION]);
  const active =
    values.sandbox === "local" &&
    selection?.machineId === values.sandbox_machine_id
      ? selection
      : null;
  const invalid =
    values.sandbox === "local" &&
    values[WORKSPACE_OPTION] !== undefined &&
    values[WORKSPACE_OPTION] !== "" &&
    !active;
  const nativeIdentityPending =
    values.sandbox === "local" && isShellAvailable() && !currentMachineId;
  const fallbackLabel = t(
    invalid
      ? "backendErrors.sandboxWorkspaceInvalid"
      : nativeIdentityPending
        ? "sessionWorkspace.choose"
        : "sessionWorkspace.independent",
  );
  // A dialog result belongs only to the options/session that opened it.
  const latest = useRef<{ values: Props["values"]; disabled: boolean } | null>(
    null,
  );
  latest.current = { values, disabled };
  useEffect(
    () => () => {
      latest.current = null;
    },
    [],
  );
  const visible = isCurrentWorkspaceMachine(
    values.sandbox,
    selectedId,
    currentMachineId,
  );
  const [previousLocations, setPreviousLocations] = useState<
    WorkspaceSelection[]
  >([]);
  const [historyFailed, setHistoryFailed] = useState(false);
  const [historyRetry, setHistoryRetry] = useState(0);
  const workspaceValue = values[WORKSPACE_OPTION];
  useEffect(() => {
    setPreviousLocations([]);
    setHistoryFailed(false);
    if (!sessionId || !visible) return;
    let cancelled = false;
    sessionApi
      .getWorkspaceLocations(sessionId)
      .then(({ locations }) => {
        if (cancelled) return;
        const selections = locations.map(({ options }) => {
          const item = parseWorkspaceSelection(options[WORKSPACE_OPTION]);
          return options.sandbox === "local" &&
            options.sandbox_machine_id === item?.machineId
            ? item
            : null;
        });
        setPreviousLocations(
          selections.filter(
            (item): item is WorkspaceSelection =>
              !!item &&
              item.machineId === currentMachineId &&
              item.id !== parseWorkspaceSelection(workspaceValue)?.id,
          ),
        );
      })
      .catch(() => {
        if (!cancelled) setHistoryFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, visible, currentMachineId, workspaceValue, historyRetry]);
  const name =
    active?.path
      .replace(/[\\/]+$/, "")
      .split(/[\\/]/)
      .pop() || active?.path;
  const choose = async () => {
    if (!onChange || disabled || picking.current || machine?.online !== true)
      return;
    const initial = values;
    picking.current = true;
    setBusy(true);
    try {
      const picked = await invokeInShell<WorkspaceSelection | null>(
        "sandbox_pick_workspace",
        { title: t("sessionWorkspace.choose") },
      );
      if (
        !picked ||
        latest.current?.values !== initial ||
        latest.current?.disabled ||
        picked.machineId !== selectedId
      )
        return;
      onChange(WORKSPACE_OPTION, JSON.stringify(picked));
      rememberLocalWorkspace(user?.id, picked);
    } catch {
      toast.error(t("sessionWorkspace.failed"));
    } finally {
      picking.current = false;
      setBusy(false);
    }
  };

  useImperativeHandle(ref, () => ({
    prepareSubmit: () => {
      if (nativeIdentityPending || picking.current) return false;
      if (!visible || active) return true;
      void choose();
      return false;
    },
  }));

  const present = (content: ReactNode) =>
    host === undefined ? content : host ? createPortal(content, host) : null;

  if (!visible || !onChange) {
    if (compact && !active && !invalid && !nativeIdentityPending) return null;
    if (values.sandbox !== "local" && values.sandbox !== "cloud") return null;
    return present(
      <div
        className="session-workspace-bar flex min-w-0 items-center gap-2 px-1 py-1 text-14 text-theme-text-secondary"
        title={t(
          nativeIdentityPending
            ? "sessionWorkspace.chooseHint"
            : active
              ? "sessionWorkspace.scope"
              : "sessionWorkspace.independentHint",
        )}
      >
        <Folder size={16} className="shrink-0" aria-hidden="true" />
        <span className="min-w-0 break-all">{name || fallbackLabel}</span>
      </div>,
    );
  }

  return present(
    <div
      className="session-workspace-bar flex min-w-0 shrink items-center gap-2 text-14"
      style={{ color: "var(--theme-text-secondary)" }}
    >
      <button
        type="button"
        onClick={() => void choose()}
        disabled={disabled || busy || machine?.online !== true}
        className="flex min-h-9 min-w-0 items-center gap-2 rounded-md px-1 py-1 text-left focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
        title={
          active
            ? `${active.path}\n${t("sessionWorkspace.scope")}`
            : t("sessionWorkspace.chooseHint")
        }
        aria-label={
          active
            ? `${t("sessionWorkspace.choose")}: ${active.path}`
            : t("sessionWorkspace.choose")
        }
      >
        {busy ? (
          <LoadingSpinner color="text-current" size={16} className="shrink-0" />
        ) : (
          <InteractiveIcon>
            <Folder size={16} className="shrink-0" />
          </InteractiveIcon>
        )}
        <span className={compact ? "truncate" : "min-w-0 break-all"}>
          {busy
            ? t("sessionWorkspace.loading")
            : name || (invalid ? fallbackLabel : t("sessionWorkspace.choose"))}
        </span>
      </button>
      {historyFailed ? (
        <button
          type="button"
          className="chat-tool-btn shrink-0"
          disabled={disabled}
          title={t("common.loadFailed")}
          aria-label={t("sessionWorkspace.previous")}
          onClick={() => setHistoryRetry((value) => value + 1)}
        >
          {t("common.retry")}
        </button>
      ) : (
        previousLocations.length > 0 && (
          <Select
            value=""
            ariaLabel={t("sessionWorkspace.previous")}
            placeholder={<History size={16} aria-hidden="true" />}
            triggerClassName="chat-tool-btn"
            className="shrink-0"
            disabled={disabled || busy || machine?.online !== true}
            options={previousLocations.map((item) => ({
              value: item.id,
              label: item.path,
            }))}
            onChange={(id) => {
              const selected = previousLocations.find((item) => item.id === id);
              if (!selected || disabled || busy || machine?.online !== true)
                return;
              onChange(WORKSPACE_OPTION, JSON.stringify(selected));
              rememberLocalWorkspace(user?.id, selected);
            }}
          />
        )
      )}
    </div>,
  );
}
