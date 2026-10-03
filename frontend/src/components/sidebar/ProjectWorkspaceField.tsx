import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, Info, Loader2, X } from "lucide-react";
import toast from "react-hot-toast";
import {
  invokeInShell,
  isShellAvailable,
} from "../../services/tauri/sandboxShell";
import { Dialog } from "../common/Dialog";
import type { Project } from "../../types";

export function ProjectWorkspaceField({
  value,
  onChange,
}: {
  value?: Project["workspace"];
  onChange: (value: Project["workspace"]) => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const shell = isShellAvailable();
  if (!shell && !value) return null;
  const change = async (clear: boolean) => {
    if (busy) return;
    setBusy(true);
    try {
      const picked = clear
        ? null
        : await invokeInShell<Project["workspace"]>("sandbox_pick_workspace", {
            title: t("projectWorkspace.choose"),
          });
      if (mounted.current && (clear || picked)) await onChange(picked);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t("common.operationFailed"),
      );
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <div className="min-w-0 space-y-1.5 px-3 py-2 text-12 text-theme-text-secondary">
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          disabled={busy || !shell}
          onClick={() => void change(false)}
          aria-label={t("projectWorkspace.choose")}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-md py-1 text-left focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
        >
          {busy ? (
            <Loader2
              size={14}
              className="shrink-0 animate-spin motion-reduce:animate-none"
            />
          ) : (
            <FolderOpen size={14} className="shrink-0" />
          )}
          <span className="truncate" title={value?.path}>
            {value?.path || t("projectWorkspace.choose")}
          </span>
        </button>
        <ProjectWorkspaceDetails value={value} />
        {value && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void change(true)}
            aria-label={t("projectWorkspace.clear")}
            className="rounded-md p-1 focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

export function ProjectWorkspaceDetails({
  value,
}: {
  value?: Project["workspace"];
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <span className="shrink-0" onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        ref={trigger}
        onClick={() => setOpen(true)}
        aria-label={t("projectWorkspace.details")}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="flex h-8 w-6 max-sm:h-9 max-sm:w-9 shrink-0 items-center justify-center rounded-md text-theme-text-tertiary focus-visible:outline focus-visible:outline-2"
      >
        <Info size={14} aria-hidden="true" />
      </button>
      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          trigger.current?.focus();
        }}
        title={t("projectWorkspace.details")}
      >
        <div className="space-y-3 text-13 text-theme-text-secondary">
          {value && (
            <p className="break-all font-mono select-text">{value.path}</p>
          )}
          <p>
            {t(
              value ? "projectWorkspace.inherits" : "projectWorkspace.optional",
            )}
          </p>
          <p>{t("projectWorkspace.privacy")}</p>
        </div>
      </Dialog>
    </span>
  );
}
