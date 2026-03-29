import { useTranslation } from "react-i18next";
import { Maximize2, X, Plus, Tag } from "lucide-react";
import { Toggle } from "./Toggle";
import { FileTabs } from "./FileTabs";
import { SkillEditor } from "./SkillEditor";
import { normalizeTags } from "./SkillForm.utils";
import type { SkillFormActions } from "./SkillForm.types";

export function SkillFormNormal(a: SkillFormActions) {
  const { t } = useTranslation();

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
              <div className="relative">
                <input
                  type="text"
                  value={a.name}
                  disabled={a.isEditing}
                  onChange={(e) => a.setName(e.target.value)}
                  placeholder={t("skills.form.namePlaceholder")}
                  className="w-full rounded-xl border border-[var(--theme-border)] px-3 py-2 font-mono text-sm text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50 bg-[var(--theme-bg)] hover:border-[var(--skill-border-strong)]"
                />
                {a.isEditing && (
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-md bg-[var(--theme-bg-card)]/80 p-1">
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
                )}
              </div>
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
              <textarea
                value={a.description}
                onChange={(e) => a.setDescription(e.target.value)}
                placeholder={t("skills.form.descriptionPlaceholder")}
                rows={3}
                className="w-full resize-none rounded-xl border border-[var(--theme-border)] px-3 py-2 text-sm leading-6 text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 transition-all duration-150 bg-[var(--theme-bg)] hover:border-[var(--skill-border-strong)]"
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
                  <Tag
                    size={12}
                    className="text-[var(--theme-primary)]"
                  />
                  {t("adminMarketplace.tags")}
                </div>
                <p className="mt-2 text-xs leading-5 text-[var(--theme-text-secondary)]/80">
                  {t("adminMarketplace.tagsHint")}
                </p>
                <input
                  type="text"
                  value={a.tagsInput}
                  onChange={(e) => a.setTagsInput(e.target.value)}
                  placeholder={t("adminMarketplace.tagsPlaceholder")}
                  className="mt-3 w-full rounded-xl border border-[var(--theme-border)] px-3 py-2 text-sm text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 transition-all duration-150 bg-[var(--theme-bg-card)] hover:border-[var(--skill-border-strong)]"
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
                  <button
                    type="button"
                    onClick={a.addFile}
                    className="flex h-9 w-9 items-center justify-center rounded-xl text-stone-400 transition-colors duration-150 hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
                    title={t("skills.form.addFile", "Add file")}
                  >
                    <Plus size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={() => a.toggleFullscreen(true)}
                    className="flex h-9 w-9 items-center justify-center rounded-xl text-stone-400 transition-colors duration-150 hover:bg-[var(--theme-bg-card)] hover:text-[var(--theme-text)]"
                    title={t("skills.form.fullscreenEditor")}
                  >
                    <Maximize2 size={15} />
                  </button>
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
                <input
                  type="text"
                  value={a.files[a.activeFileIndex]?.path || ""}
                  onChange={(e) =>
                    a.updateFilePath(a.activeFileIndex, e.target.value)
                  }
                  placeholder={t("skills.form.filePathPlaceholder")}
                  className="w-full bg-transparent font-mono text-xs text-[var(--theme-text)] placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* Editor */}
          <div className="flex-1 min-h-0 p-3 sm:p-4">
            <div
              className={`flex h-full min-h-[18rem] sm:min-h-[24rem] flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg)] transition-colors duration-150 ${
                a.errors.content
                  ? "ring-1 ring-red-300 dark:ring-red-700"
                  : ""
              } skill-editor-shell`}
            >
              <SkillEditor
                value={a.files[a.activeFileIndex]?.content || ""}
                onChange={(val) => a.updateFileContent(a.activeFileIndex, val)}
                className="flex-1 min-h-0"
                filePath={a.files[a.activeFileIndex]?.path}
              />
            </div>
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
        <button
          type="button"
          onClick={a.onCancel}
          disabled={a.isLoading}
          className="rounded-xl px-4 py-2 text-sm text-[var(--theme-text)] hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors duration-150"
        >
          {t("common.cancel")}
        </button>
        <button
          type="submit"
          disabled={a.isLoading}
          className="rounded-xl bg-[var(--theme-primary)] px-5 py-2 text-sm font-medium text-white hover:bg-[var(--theme-primary-hover)] disabled:opacity-50 transition-colors duration-150 dark:text-stone-950 inline-flex items-center gap-2"
        >
          {a.isLoading ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="loading-text">{t("common.saving", "Saving...")}</span>
            </>
          ) : a.isEditing ? (
            t("skills.form.saveChanges")
          ) : (
            t("skills.form.createSkill")
          )}
        </button>
      </div>
    </>
  );
}
