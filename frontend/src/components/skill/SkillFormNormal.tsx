import { useTranslation } from "react-i18next";
import { Maximize2, X, Plus, Save, Pencil, Upload } from "lucide-react";
import { ToggleSwitch } from "../panels/AgentPanel/shared/ToggleSwitch";
import {
  Button,
  ToolbarIconButton,
  FormField,
  Input,
  Textarea,
} from "../common";
import { FileTabs } from "./FileTabs";
import { SkillEditor } from "./SkillEditor";
import { BinaryFilePreview } from "./BinaryFilePreview";
import { normalizeTags } from "./SkillForm.utils";
import type { SkillFormActions } from "./SkillForm.types";

export function SkillFormNormal(a: SkillFormActions) {
  const { t } = useTranslation();
  const submitLabel = a.isEditing
    ? t("skills.form.saveChanges")
    : t("skills.form.createSkill");

  return (
    <>
      <div className="flex flex-1 flex-col gap-4">
        {/* Metadata card */}
        <div className="skill-form-card rounded-3xl shadow-sm">
          <div className="space-y-4 px-4 py-4 sm:px-5">
            <FormField
              label={t("skills.form.name")}
              error={a.errors.name}
              hint={a.isEditing ? t("skills.form.nameCannotChange") : undefined}
            >
              <Input
                type="text"
                value={a.name}
                disabled={a.isEditing}
                onChange={(e) => a.setName(e.target.value)}
                placeholder={t("skills.form.namePlaceholder")}
                error={!!a.errors.name}
                className="font-mono"
              />
            </FormField>
            <FormField
              label={t("skills.form.description")}
              error={a.errors.description}
            >
              <Textarea
                value={a.description}
                onChange={(e) => a.setDescription(e.target.value)}
                placeholder={t("skills.form.descriptionPlaceholder")}
                rows={5}
                error={!!a.errors.description}
                className="resize-y leading-6"
              />
            </FormField>
            <FormField
              label={t("adminMarketplace.tags")}
              hint={t("adminMarketplace.tagsHint")}
              error={a.errors.tags}
            >
              <Input
                type="text"
                value={a.tagsInput}
                data-skill-tags
                onChange={(e) => a.setTagsInput(e.target.value)}
                placeholder={t("adminMarketplace.tagsPlaceholder")}
                error={!!a.errors.tags}
              />
              {normalizeTags(a.tagsInput).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {normalizeTags(a.tagsInput).map((tag) => (
                    <span
                      key={tag}
                      className="skill-tag-chip skill-tag-chip--active"
                    >
                      {tag}
                      <button
                        type="button"
                        onClick={() => a.removeTag(tag)}
                        className="skill-tag-chip-remove"
                        aria-label={`${t("common.remove")}: ${tag}`}
                      >
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </FormField>

            {/* Enabled toggle */}
            <div className="skill-toggle-panel flex items-center justify-between rounded-2xl bg-[var(--theme-bg-subtle)] px-3 py-3">
              <div className="min-w-0 pr-3">
                <p className="text-14 font-medium text-[var(--theme-text)]">
                  {t("skills.form.enabled")}
                </p>
                <p className="mt-1 text-12 text-[var(--theme-text-secondary)]">
                  {a.enabled
                    ? t("skills.form.enabledHint")
                    : t("skills.form.disabledHint")}
                </p>
              </div>
              <div className="shrink-0">
                <ToggleSwitch
                  enabled={a.enabled}
                  onToggle={() => a.setEnabled(!a.enabled)}
                  ariaLabel={t("skills.form.enabled")}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Editor area */}
        <div className="skill-form-editor flex flex-col overflow-hidden rounded-3xl shadow-sm">
          <div className="shrink-0 px-3 py-3 sm:px-4">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3 font-sans">
                <p className="text-11 font-semibold uppercase tracking-[0.18em] text-[var(--theme-text-secondary)]/80">
                  {t("skills.form.files", "Files")}
                </p>
                <div className="flex items-center gap-1 shrink-0">
                  <ToolbarIconButton
                    aria-label={t("skills.form.addFile", "Add file")}
                    onClick={a.addFile}
                    icon={<Plus size={15} />}
                    variant="muted"
                    title={t("skills.form.addFile", "Add file")}
                  />
                  <ToolbarIconButton
                    aria-label={t(
                      "skills.form.addBinaryFile",
                      "Upload binary file",
                    )}
                    onClick={a.addBinaryFile}
                    icon={<Upload size={15} />}
                    variant="muted"
                    title={t("skills.form.addBinaryFile", "Upload binary file")}
                  />
                  <ToolbarIconButton
                    aria-label={t("skills.form.fullscreenEditor")}
                    data-fullscreen-trigger
                    onClick={() => a.toggleFullscreen(true)}
                    icon={<Maximize2 size={15} />}
                    variant="muted"
                    title={t("skills.form.fullscreenEditor")}
                  />
                </div>
              </div>

              <div className="skill-file-tabs min-w-0 overflow-hidden rounded-2xl px-1 py-1">
                <FileTabs
                  files={a.files}
                  activeFileIndex={a.activeFileIndex}
                  onSelect={a.setActiveFileIndex}
                  onRemove={a.removeFile}
                  untitledLabel={t("skills.form.untitled")}
                />
              </div>

              <div className="skill-file-path rounded-2xl px-3 py-2.5">
                <FormField label={t("skills.form.filePath")}>
                  <Input
                    type="text"
                    value={a.files[a.activeFileIndex]?.path || ""}
                    onChange={(e) =>
                      a.updateFilePath(a.activeFileIndex, e.target.value)
                    }
                    placeholder={t("skills.form.filePathPlaceholder")}
                    className="bg-transparent font-mono text-12"
                  />
                </FormField>
              </div>
            </div>
          </div>

          {/* Editor / Binary Preview */}
          <div className="flex-1 min-h-0 p-3 sm:p-4">
            {(() => {
              const currentPath = a.files[a.activeFileIndex]?.path || "";
              const binaryInfo = a.binaryFiles?.[currentPath];

              // Loading state
              if (a.loadingFilePath === currentPath) {
                return (
                  <div className="flex h-full min-h-[18rem] sm:min-h-[24rem] items-center justify-center rounded-2xl bg-[var(--theme-bg-subtle)]">
                    <div className="flex flex-col items-center gap-3">
                      <svg
                        className="h-6 w-6 animate-spin text-[var(--theme-text-secondary)]"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                          fill="none"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        />
                      </svg>
                      <span className="text-14 text-[var(--theme-text-secondary)]">
                        {currentPath.split("/").pop()}
                      </span>
                    </div>
                  </div>
                );
              }

              if (binaryInfo) {
                return (
                  <BinaryFilePreview
                    url={binaryInfo.url}
                    mime_type={binaryInfo.mime_type}
                    size={binaryInfo.size}
                    fileName={currentPath.split("/").pop() || currentPath}
                  />
                );
              }
              return (
                <div
                  className={`relative flex flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg-subtle)] transition-colors duration-150 ${
                    a.errors.content
                      ? "ring-1 ring-red-300 dark:ring-red-700"
                      : ""
                  }`}
                  style={{ height: "180px" }}
                >
                  <SkillEditor
                    value={a.files[a.activeFileIndex]?.content || ""}
                    onChange={(val) =>
                      a.updateFileContent(a.activeFileIndex, val)
                    }
                    className="h-full"
                    filePath={a.files[a.activeFileIndex]?.path}
                    readOnly
                  />
                  <div className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-[var(--theme-bg)] to-transparent" />
                  <Button
                    variant="primary"
                    onClick={() => a.toggleFullscreen(true)}
                    leftIcon={<Pencil size={12} />}
                    className="absolute right-3 bottom-3 shadow-md"
                  >
                    {t("skills.form.editFullscreen", "Edit")}
                  </Button>
                </div>
              );
            })()}
            {(a.errors.content || a.errors.files) && (
              <p className="mt-2 text-12 text-red-500">
                {a.errors.content || a.errors.files}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Bottom action bar */}
      <div className="skill-action-bar shrink-0 flex items-center justify-end gap-2 px-1 pt-3">
        <Button variant="ghost" onClick={a.onCancel} disabled={a.isLoading}>
          {t("common.cancel")}
        </Button>
        <Button
          type="submit"
          variant="primary"
          loading={a.isLoading}
          leftIcon={<Save size={16} />}
        >
          <span className={a.isLoading ? "loading-text" : ""}>
            {submitLabel}
          </span>
        </Button>
      </div>
    </>
  );
}
