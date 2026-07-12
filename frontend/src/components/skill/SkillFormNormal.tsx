import { useTranslation } from "react-i18next";
import { Maximize2, X, Plus, Save, Tag, Pencil, Upload } from "lucide-react";
import { Toggle } from "./Toggle";
import { Button, IconButton, Input, Textarea } from "../common";
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
            {/* Name */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[var(--theme-text-secondary)]">
                {t("skills.form.name")}
              </label>
              <Input
                type="text"
                value={a.name}
                disabled={a.isEditing}
                onChange={(e) => a.setName(e.target.value)}
                placeholder={t("skills.form.namePlaceholder")}
                error={!!a.errors.name}
                className="font-mono"
                trailingSlot={
                  a.isEditing ? (
                    <span className="pointer-events-none rounded-md bg-[var(--theme-bg-card)]/80 p-1">
                      <svg
                        className="h-4 w-4 text-stone-400 dark:text-stone-500"
                        viewBox="0 0 16 16"
                        fill="none"
                      >
                        <rect
                          x="2"
                          y="2"
                          width="12"
                          height="12"
                          rx="3"
                          stroke="currentColor"
                          strokeWidth="1.2"
                        />
                        <path
                          d="M6 8h4M8 6v4"
                          stroke="currentColor"
                          strokeWidth="1.2"
                          strokeLinecap="round"
                        />
                      </svg>
                    </span>
                  ) : null
                }
              />
              {a.errors.name && (
                <p className="text-xs text-red-500">{a.errors.name}</p>
              )}
              {a.isEditing && !a.errors.name && (
                <p className="text-xs text-stone-400 dark:text-stone-500">
                  {t("skills.form.nameCannotChange")}
                </p>
              )}
            </div>

            {/* Description */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[var(--theme-text-secondary)]">
                {t("skills.form.description")}
              </label>
              <Textarea
                value={a.description}
                onChange={(e) => a.setDescription(e.target.value)}
                placeholder={t("skills.form.descriptionPlaceholder")}
                rows={5}
                error={!!a.errors.description}
                className="resize-none leading-6"
              />
              {a.errors.description && (
                <p className="text-xs text-red-500">{a.errors.description}</p>
              )}
            </div>

            {/* Tags */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[var(--theme-text-secondary)]">
                {t("adminMarketplace.tags")}
              </label>
              <div className="skill-tag-editor rounded-2xl bg-[var(--theme-bg)] p-3 shadow-sm">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]/80">
                  <Tag size={12} className="text-[var(--theme-primary)]" />
                  {t("adminMarketplace.tags")}
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--theme-text-secondary)]/80">
                  {t("adminMarketplace.tagsHint")}
                </p>
                <Input
                  type="text"
                  value={a.tagsInput}
                  onChange={(e) => a.setTagsInput(e.target.value)}
                  placeholder={t("adminMarketplace.tagsPlaceholder")}
                  error={!!a.errors.tags}
                  className="mt-3"
                />
                <div className="mt-3 flex flex-wrap gap-2">
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
                        aria-label={`Remove tag ${tag}`}
                      >
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                  {normalizeTags(a.tagsInput).length === 0 && (
                    <span className="text-xs text-[var(--theme-text-secondary)]/80">
                      {t("adminMarketplace.tagsPlaceholder")}
                    </span>
                  )}
                </div>
              </div>
              {a.errors.tags && (
                <p className="text-xs text-red-500">{a.errors.tags}</p>
              )}
            </div>

            {/* Enabled toggle */}
            <div className="skill-toggle-panel flex items-center justify-between rounded-2xl bg-[var(--theme-bg)] px-3 py-3">
              <div className="min-w-0 pr-3">
                <p className="text-sm font-medium text-[var(--theme-text)]">
                  {t("skills.form.enabled")}
                </p>
                <p className="mt-1 text-xs text-[var(--theme-text-secondary)]">
                  {a.enabled
                    ? t("skills.form.enabledHint")
                    : t("skills.form.disabledHint")}
                </p>
              </div>
              <div className="shrink-0">
                <Toggle
                  checked={a.enabled}
                  onChange={a.setEnabled}
                  label={t("skills.form.enabled")}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Editor area */}
        <div className="skill-form-editor flex flex-col overflow-hidden rounded-3xl shadow-sm">
          <div className="shrink-0 px-3 py-3 sm:px-4">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--theme-text-secondary)]/80">
                  {t("skills.form.files", "Files")}
                </p>
                <div className="flex items-center gap-1 shrink-0">
                  <IconButton
                    aria-label={t("skills.form.addFile", "Add file")}
                    onClick={a.addFile}
                    icon={<Plus size={15} />}
                    size="sm"
                    className="h-9 w-9 rounded-xl text-stone-400 hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
                    title={t("skills.form.addFile", "Add file")}
                  />
                  <IconButton
                    aria-label={t(
                      "skills.form.addBinaryFile",
                      "Upload binary file",
                    )}
                    onClick={a.addBinaryFile}
                    icon={<Upload size={15} />}
                    size="sm"
                    className="h-9 w-9 rounded-xl text-stone-400 hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
                    title={t("skills.form.addBinaryFile", "Upload binary file")}
                  />
                  <IconButton
                    aria-label={t("skills.form.editFullscreen", "Edit")}
                    onClick={() => a.toggleFullscreen(true)}
                    icon={<Pencil size={15} />}
                    size="sm"
                    className="h-9 w-9 rounded-xl text-stone-400 hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
                    title={t("skills.form.editFullscreen", "Edit")}
                  />
                  <IconButton
                    aria-label={t("skills.form.fullscreenEditor")}
                    onClick={() => a.toggleFullscreen(true)}
                    icon={<Maximize2 size={15} />}
                    size="sm"
                    className="h-9 w-9 rounded-xl text-stone-400 hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
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
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]/80">
                  {t("skills.form.filePath")}
                </label>
                <Input
                  type="text"
                  value={a.files[a.activeFileIndex]?.path || ""}
                  onChange={(e) =>
                    a.updateFilePath(a.activeFileIndex, e.target.value)
                  }
                  placeholder={t("skills.form.filePathPlaceholder")}
                  className="bg-transparent font-mono text-xs"
                />
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
                  <div className="flex h-full min-h-[18rem] sm:min-h-[24rem] items-center justify-center rounded-2xl bg-[var(--theme-bg)]">
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
                      <span className="text-sm text-[var(--theme-text-secondary)]">
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
                  className={`relative flex flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg)] transition-colors duration-150 ${
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
                    size="sm"
                    onClick={() => a.toggleFullscreen(true)}
                    leftIcon={<Pencil size={12} />}
                    className="absolute right-3 bottom-3 shadow-md transition-transform duration-150 hover:scale-105 active:scale-95"
                  >
                    {t("skills.form.editFullscreen", "Edit")}
                  </Button>
                </div>
              );
            })()}
            {(a.errors.content || a.errors.files) && (
              <p className="mt-2 text-xs text-red-500">
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
