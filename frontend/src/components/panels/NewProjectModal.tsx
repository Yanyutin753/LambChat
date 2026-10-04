import { DialogCloseButton } from "../common/DialogCloseButton";
import { ModalSurface } from "../common/ModalSurface";

import { useTranslation } from "react-i18next";
import type { Project } from "../../types";
import { ProjectWorkspaceField } from "../sidebar/ProjectWorkspaceField";

interface NewProjectModalProps {
  icon: string;
  name: string;
  onIconChange: (icon: string) => void;
  onNameChange: (name: string) => void;
  onCreate: () => void;
  onClose: () => void;
  workspace?: Project["workspace"];
  onWorkspaceChange?: (workspace: Project["workspace"]) => void;
}

export function NewProjectModal({
  icon,
  name,
  onIconChange,
  onNameChange,
  onCreate,
  onClose,
  workspace,
  onWorkspaceChange,
}: NewProjectModalProps) {
  const { t } = useTranslation();

  return (
    <ModalSurface open={true} onClose={onClose} dismissible={true}>
      <div className="relative bg-theme-bg-card rounded-xl shadow-2xl p-5 w-[90vw] max-w-md space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="min-w-0 text-14 font-semibold font-sans text-stone-800 dark:text-stone-100">
            {t("sidebar.newProject")}
          </h3>
          <DialogCloseButton onClick={onClose} />
        </div>
        <p className="text-12 text-stone-400 dark:text-stone-500">
          {t("sidebar.projectHint")}
        </p>

        <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-stone-200 dark:border-stone-600 bg-theme-bg-subtle dark:bg-stone-700/50 focus-within:ring-2 focus-within:ring-stone-400/50 focus-within:border-stone-300 dark:focus-within:border-stone-500 transition-all">
          <input
            type="text"
            value={icon}
            onChange={(e) => onIconChange(e.target.value)}
            placeholder={t("sidebar.projectName")}
            className="w-8 text-14 bg-transparent text-stone-500 dark:text-stone-400 placeholder-stone-400 focus:outline-none"
          />
          <div className="w-px h-5 bg-stone-300 dark:bg-stone-600" />
          <input
            ref={(el) => {
              if (el) el.focus();
            }}
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing || e.keyCode === 229) return;
              if (e.key === "Enter") {
                e.preventDefault();
                onCreate();
                onClose();
              }
              if (e.key === "Escape") {
                e.preventDefault();
                onClose();
                onNameChange("");
              }
            }}
            placeholder={t("sidebar.projectName")}
            className="flex-1 text-14 bg-transparent text-stone-700 dark:text-stone-200 placeholder-stone-400 focus:outline-none"
          />
        </div>
        {onWorkspaceChange && (
          <ProjectWorkspaceField
            value={workspace}
            onChange={onWorkspaceChange}
          />
        )}
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={() => {
              onClose();
              onNameChange("");
              onIconChange("📁");
            }}
            className="px-4 py-2 text-14 font-medium text-stone-600 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 transition-all"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={() => {
              onCreate();
              onClose();
            }}
            disabled={!name.trim()}
            className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t("common.create")}
          </button>
        </div>
      </div>
    </ModalSurface>
  );
}
