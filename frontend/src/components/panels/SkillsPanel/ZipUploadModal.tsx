import { useTranslation } from "react-i18next";
import { X, Archive, UploadCloud, FileArchive, Upload } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { Checkbox } from "../../common/Checkbox";
import type { ZipSkillPreview } from "./useSkillsActions";
import { useSwipeToClose } from "../../../hooks/useSwipeToClose";

interface ZipUploadModalProps {
  showZipModal: boolean;
  setShowZipModal: (show: boolean) => void;
  zipFile: File | null;
  zipUploading: boolean;
  zipPreviewing: boolean;
  zipSkills: ZipSkillPreview[];
  selectedZipSkills: string[];
  zipInputRef: React.RefObject<HTMLInputElement | null>;
  isDragging: boolean;
  onZipFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onZipSkillToggle: (name: string) => void;
  onZipSelectAll: (names: string[]) => void;
  onZipUpload: () => void;
}

export function ZipUploadModal({
  showZipModal,
  setShowZipModal,
  zipFile,
  zipUploading,
  zipPreviewing,
  zipSkills,
  selectedZipSkills,
  zipInputRef,
  isDragging,
  onZipFileChange,
  onDragOver,
  onDragLeave,
  onDrop,
  onZipSkillToggle,
  onZipSelectAll,
  onZipUpload,
}: ZipUploadModalProps) {
  const { t } = useTranslation();
  const swipeRef = useSwipeToClose({
    onClose: () => setShowZipModal(false),
    enabled: showZipModal,
  });

  if (!showZipModal) return null;

  const newCount = zipSkills.filter((s) => !s.already_exists).length;

  return (
    <>
      <div
        className="fixed inset-0 z-[299] bg-black/50 sm:bg-transparent"
        onClick={
          zipUploading || zipPreviewing
            ? undefined
            : () => setShowZipModal(false)
        }
      />
      <div
        data-disable-global-file-drop="true"
        className="modal-bottom-sheet sm:modal-centered-wrapper"
        onClick={
          zipUploading || zipPreviewing
            ? undefined
            : () => setShowZipModal(false)
        }
      >
        <div
          ref={swipeRef as React.RefObject<HTMLDivElement>}
          className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]"
        >
          <div className="bottom-sheet-handle sm:hidden" />
          <div className="skill-modal-header">
            <div>
              <h3 className="skill-modal-header__title">
                {t("skills.uploadZipTitle")}
              </h3>
              <p className="skill-modal-header__subtitle">
                {t("skills.subtitle")}
              </p>
            </div>
            <button
              onClick={() => setShowZipModal(false)}
              disabled={zipUploading || zipPreviewing}
              className="btn-icon disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <X size={20} />
            </button>
          </div>
          <div className="skill-modal-body flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
            <div className="skill-modal-section space-y-4">
              {/* Drag & Drop / Click Upload Zone */}
              <div
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                onClick={() => zipInputRef.current?.click()}
                className={`group relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 transition-all duration-200 ${
                  isDragging
                    ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)]/40 scale-[1.01]"
                    : "border-[var(--theme-border)] bg-[var(--theme-bg)]/60 hover:border-[var(--theme-primary)]/50 hover:bg-[var(--theme-bg)]/90"
                } ${zipPreviewing ? "pointer-events-none opacity-60" : ""}`}
              >
                <input
                  ref={zipInputRef}
                  type="file"
                  accept=".zip"
                  onChange={onZipFileChange}
                  className="hidden"
                />
                <div
                  className={`flex h-14 w-14 items-center justify-center rounded-2xl transition-all duration-200 ${
                    isDragging
                      ? "bg-[var(--theme-primary)] text-white shadow-lg shadow-[var(--theme-primary)]/20 scale-110"
                      : "bg-[var(--theme-primary-light)] text-[var(--theme-primary)] group-hover:scale-105"
                  }`}
                >
                  {isDragging ? (
                    <FileArchive size={24} />
                  ) : (
                    <UploadCloud size={24} />
                  )}
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-[var(--theme-text)]">
                    {isDragging
                      ? t("skills.dropZoneActive")
                      : t("skills.dropZoneTitle")}
                  </p>
                  <p className="mt-1 text-xs text-[var(--theme-text-secondary)]">
                    {t("skills.dropZoneHint")}
                  </p>
                </div>
                {zipFile && (
                  <div className="flex items-center gap-2 rounded-xl bg-[var(--theme-primary-light)]/60 px-3 py-1.5">
                    <Archive
                      size={14}
                      className="text-[var(--theme-primary)]"
                    />
                    <span className="text-xs font-medium text-[var(--theme-text)]">
                      {zipFile.name}
                    </span>
                    <span className="text-xs text-[var(--theme-text-secondary)]">
                      ({(zipFile.size / 1024).toFixed(1)} KB)
                    </span>
                  </div>
                )}
              </div>

              {zipPreviewing && (
                <div className="flex items-center justify-center gap-2 py-3 text-sm text-[var(--theme-text-secondary)]">
                  <LoadingSpinner size="sm" />
                  {t("skills.preview")}
                </div>
              )}

              {zipSkills.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <label className="text-sm font-medium text-[var(--theme-text)]">
                        {t("skills.selectSkillsToInstall")}
                      </label>
                      <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary)]/10 px-1.5 text-[11px] font-semibold text-[var(--theme-primary)]">
                        {selectedZipSkills.length}/{newCount}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        const allNew = zipSkills
                          .filter((s) => !s.already_exists)
                          .map((s) => s.name);
                        onZipSelectAll(
                          selectedZipSkills.length === allNew.length
                            ? []
                            : allNew,
                        );
                      }}
                      className="rounded-md px-2 py-1 text-xs font-medium text-[var(--theme-primary)] transition-colors hover:bg-[var(--theme-primary)]/8"
                    >
                      {selectedZipSkills.length === newCount
                        ? t("common.deselectAll")
                        : t("common.selectAll")}
                    </button>
                  </div>
                  <div className="space-y-1.5 max-h-72 overflow-y-auto rounded-xl p-1">
                    {zipSkills.map((skill) => {
                      const selected = selectedZipSkills.includes(skill.name);
                      return (
                        <div
                          key={skill.name}
                          onClick={() =>
                            !skill.already_exists &&
                            onZipSkillToggle(skill.name)
                          }
                          className={`group flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-150 ${
                            skill.already_exists
                              ? "cursor-not-allowed opacity-40"
                              : selected
                                ? "bg-[var(--theme-primary)]/8"
                                : "hover:bg-[var(--theme-primary)]/4"
                          }`}
                        >
                          <Checkbox
                            size="sm"
                            checked={selected}
                            onChange={() =>
                              !skill.already_exists &&
                              onZipSkillToggle(skill.name)
                            }
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p
                                className={`text-sm font-medium truncate transition-colors ${
                                  selected
                                    ? "text-[var(--theme-primary)]"
                                    : "text-[var(--theme-text)]"
                                }`}
                              >
                                {skill.name}
                              </p>
                              {skill.already_exists && (
                                <span className="shrink-0 rounded-full bg-[var(--theme-primary)]/8 px-1.5 py-0.5 text-[10px] font-medium text-[var(--theme-primary)]/70">
                                  {t("skills.installed")}
                                </span>
                              )}
                              {!skill.already_exists &&
                                skill.file_count > 1 && (
                                  <span className="shrink-0 text-[10px] text-[var(--theme-text-secondary)]">
                                    {skill.file_count} files
                                  </span>
                                )}
                            </div>
                            {skill.description && (
                              <p className="mt-0.5 text-xs text-[var(--theme-text-secondary)] truncate">
                                {skill.description}
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 border-t border-[color-mix(in_srgb,var(--theme-border)_40%,transparent)] pt-4">
                <button
                  onClick={() => setShowZipModal(false)}
                  className="btn-secondary"
                >
                  {t("common.cancel")}
                </button>
                {zipSkills.length > 0 && (
                  <button
                    onClick={onZipUpload}
                    disabled={zipUploading || selectedZipSkills.length === 0}
                    className="btn-primary disabled:opacity-50"
                  >
                    {zipUploading ? (
                      <>
                        <LoadingSpinner size="sm" color="text-white" />
                        {t("skills.installing")}
                      </>
                    ) : (
                      <>
                        <Upload size={18} />
                        {t("skills.install")} ({selectedZipSkills.length})
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
