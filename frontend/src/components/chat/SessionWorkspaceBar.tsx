import { useRef, useState } from "react";
import { Folder, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "react-hot-toast";
import { useSandboxStatus } from "../../hooks/useSandboxStatus";
import { invokeInShell } from "../../services/tauri/sandboxShell";
import {
  isCurrentWorkspaceMachine,
  parseWorkspaceSelection,
  WORKSPACE_OPTION,
  type WorkspaceSelection,
} from "./workspaceSelection";

interface Props {
  values: Record<string, boolean | string | number>;
  onChange?: (key: string, value: string) => void;
  disabled: boolean;
}

/** A session-level directory entry; the native picker creates a local binding. */
export function SessionWorkspaceBar({ values, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const { machines, currentMachineId, defaultMachineId } = useSandboxStatus();
  const [busy, setBusy] = useState(false);
  const onlineMachines = machines.filter((item) => item.online);
  const selectedId = String(
    values.sandbox_machine_id ||
      defaultMachineId ||
      (onlineMachines.length === 1 ? onlineMachines[0].machine_id : ""),
  );
  const machine = machines.find((item) => item.machine_id === selectedId);
  const selection = parseWorkspaceSelection(values[WORKSPACE_OPTION]);
  const active = selection?.machineId === selectedId ? selection : null;
  // A dialog result belongs only to the options/session that opened it.
  const latest = useRef(values);
  latest.current = values;
  const visible = isCurrentWorkspaceMachine(
    values.sandbox,
    selectedId,
    currentMachineId,
    machine?.online === true,
  );
  if (!visible || !onChange) return null;

  const choose = async () => {
    const initial = values;
    setBusy(true);
    try {
      const picked = await invokeInShell<WorkspaceSelection | null>(
        "sandbox_pick_workspace",
        { title: t("sessionWorkspace.choose") },
      );
      if (
        !picked ||
        latest.current !== initial ||
        picked.machineId !== selectedId
      )
        return;
      onChange("sandbox_machine_id", selectedId);
      onChange(WORKSPACE_OPTION, JSON.stringify(picked));
    } catch {
      toast.error(t("sessionWorkspace.failed"));
    } finally {
      setBusy(false);
    }
  };

  const name =
    active?.path
      .replace(/[\\/]+$/, "")
      .split(/[\\/]/)
      .pop() || active?.path;
  return (
    <div
      className="session-workspace-bar flex min-w-0 shrink-0 items-center gap-2 text-14"
      style={{ color: "var(--theme-text-primary)" }}
    >
      <button
        type="button"
        onClick={() => void choose()}
        disabled={disabled || busy}
        className="flex min-h-9 min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
        title={
          active
            ? `${active.path}\n${t("sessionWorkspace.scope")}`
            : t("sessionWorkspace.scope")
        }
        aria-label={
          active
            ? `${t("sessionWorkspace.choose")}: ${active.path}`
            : t("sessionWorkspace.choose")
        }
      >
        {busy ? (
          <Loader2
            size={16}
            className="shrink-0 animate-spin motion-reduce:animate-none"
          />
        ) : (
          <Folder size={16} className="shrink-0" />
        )}
        <span className="truncate">
          {busy
            ? t("sessionWorkspace.loading")
            : name || t("sessionWorkspace.choose")}
        </span>
      </button>
      {active && (
        <button
          type="button"
          onClick={() => onChange(WORKSPACE_OPTION, "")}
          disabled={disabled || busy}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
          title={t("sessionWorkspace.reset")}
          aria-label={t("sessionWorkspace.reset")}
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
