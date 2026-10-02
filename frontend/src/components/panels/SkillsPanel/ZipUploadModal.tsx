import { useTranslation } from "react-i18next";
import { Archive, UploadCloud, FileArchive, Upload } from "lucide-react";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { EditorSidebar } from "../../common/EditorSidebar";
import { Checkbox } from "../../common/Checkbox";
import { Button } from "../../common";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";
import type { ZipSkillPreview } from "./useSkillsActions";

interface ZipUploadModalProps {
  showZipModal: boolean;
  setShowZipModal: (show: boolean) => void;
  zipFile: File | null;
  zipUploading: boolean;
  zipPreviewing: boolean;
  zipError?: string | null;
  onZipRetry?: () => void;
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
  zipError,
  onZipRetry,
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

  const newCount = zipSkills.filter((s) => !s.already_exists).length;

  return (
    <EditorSidebar
      open={showZipModal}
      onClose={() => setShowZipModal(false)}
      title={t("skills.uploadZipTitle")}
      subtitle={t("skills.subtitle")}
      icon={<Archive size={16} />}
      width="wide"
      footer={
        <div className="flex flex-wrap justify-end gap-1">
          <Button
            variant="secondary"
            onClick={() => setShowZipModal(false)}
            disabled={zipUploading || zipPreviewing}
          >
            {t("common.cancel")}
          </Button>
          {zipSkills.length > 0 && (
            <Button
              variant="primary"
              aria-label={t("skills.installSelected", {
                count: selectedZipSkills.length,
              })}
              onClick={onZipUpload}
              disabled={zipUploading || selectedZipSkills.length === 0}
            >
              {zipUploading ? (
                <LoadingSpinner size="sm" color="text-white" />
              ) : (
                <Upload size={16} />
              )}
              <span>
                {t("skills.installSelected", {
                  count: selectedZipSkills.length,
                })}
              </span>
            </Button>
          )}
        </div>
      }
    >
      <div data-disable-global-file-drop="true" className="es-form">
        <input
          ref={zipInputRef}
          type="file"
          accept=".zip"
          onChange={onZipFileChange}
          className="hidden"
        />
        {/* Drag & Drop / Click Upload Zone */}
        <button
          type="button"
          aria-label={t("skills.dropZoneTitle")}
          disabled={zipPreviewing || zipUploading}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={(e) => {
            e.stopPropagation();
            zipInputRef.current?.click();
          }}
          className={`group relative flex w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-6 sm:py-10 transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] ${
            isDragging
              ? "border-[var(--theme-primary)] bg-[var(--theme-primary-light)]/40 scale-[1.01]"
              : "border-[var(--theme-border)] bg-[var(--theme-bg-subtle)]/60 hover:border-[var(--theme-primary)]/50 hover:bg-[var(--theme-bg-subtle)]/90"
          } ${zipPreviewing ? "pointer-events-none opacity-60" : ""}`}
        >
          <div
            className={`flex h-14 w-14 items-center justify-center rounded-2xl transition-all duration-200 ${
              isDragging
                ? "bg-[var(--theme-primary)] text-white shadow-lg shadow-[var(--theme-primary)]/20 scale-110"
                : "bg-[var(--theme-primary-light)] text-[var(--theme-primary)] group-hover:scale-105"
            }`}
          >
            {isDragging ? <FileArchive size={24} /> : <UploadCloud size={24} />}
          </div>
          <div className="text-center">
            <p className="text-14 font-medium text-[var(--theme-text)]">
              {isDragging
                ? t("skills.dropZoneActive")
                : t("skills.dropZoneTitle")}
            </p>
            <p className="mt-1 text-12 text-[var(--theme-text-secondary)]">
              {t("skills.dropZoneHint")}
            </p>
          </div>
          {zipFile && (
            <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2 rounded-lg bg-theme-primary-light px-3 py-1.5">
              <Archive
                size={14}
                className="text-[var(--theme-primary)] shrink-0"
              />
              <span className="text-12 font-medium text-[var(--theme-text)] truncate max-w-[200px]">
                {zipFile.name}
              </span>
              <span className="text-12 text-[var(--theme-text-secondary)]">
                ({(zipFile.size / 1024).toFixed(1)} KB)
              </span>
            </div>
          )}
        </button>

        {zipError && (
          <div className="space-y-2">
            <ConfigPanelErrorCallout message={zipError} />
            <Button
              onClick={(event) => {
                event.currentTarget
                  .closest<HTMLElement>("[data-right-panel-root]")
                  ?.focus();
                onZipRetry?.();
              }}
              disabled={zipPreviewing || zipUploading}
            >
              {t("common.retry")}
            </Button>
          </div>
        )}

        {zipPreviewing && (
          <div className="flex items-center justify-center gap-2 py-3 text-14 text-[var(--theme-text-secondary)]">
            <LoadingSpinner size="sm" />
            {t("skills.preview")}
          </div>
        )}

        {zipSkills.length > 0 && (
          <div className="es-section space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <label className="text-14 font-medium text-[var(--theme-text)]">
                  {t("skills.selectSkillsToInstall")}
                </label>
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary)]/10 px-1.5 text-11 font-semibold text-[var(--theme-primary)]">
                  {selectedZipSkills.length}/{newCount}
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                disabled={zipPreviewing || zipUploading}
                onClick={() => {
                  const allNew = zipSkills
                    .filter((s) => !s.already_exists)
                    .map((s) => s.name);
                  onZipSelectAll(
                    selectedZipSkills.length === allNew.length ? [] : allNew,
                  );
                }}
              >
                {selectedZipSkills.length === newCount
                  ? t("common.deselectAll")
                  : t("common.selectAll")}
              </Button>
            </div>
            <div className="space-y-1.5">
              {zipSkills.map((skill) => {
                const selected = selectedZipSkills.includes(skill.name);
                return (
                  <label
                    key={skill.name}
                    className={`group flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-150 ${
                      skill.already_exists
                        ? "cursor-not-allowed opacity-40"
                        : selected
                          ? "bg-[var(--theme-primary)]/8"
                          : "hover:bg-[var(--theme-primary)]/4"
                    }`}
                  >
                    <Checkbox
                      ariaLabel={skill.name}
                      disabled={
                        skill.already_exists || zipUploading || zipPreviewing
                      }
                      size="sm"
                      checked={selected}
                      onChange={() =>
                        !skill.already_exists && onZipSkillToggle(skill.name)
                      }
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p
                          className={`min-w-0 text-14 font-medium [overflow-wrap:anywhere] transition-colors ${
                            selected
                              ? "text-[var(--theme-primary)]"
                              : "text-[var(--theme-text)]"
                          }`}
                        >
                          {skill.name}
                        </p>
                        {skill.already_exists && (
                          <span className="shrink-0 rounded-full bg-[var(--theme-primary)]/8 px-1.5 py-0.5 text-10 font-medium text-[var(--theme-primary)]/70">
                            {t("skills.installed")}
                          </span>
                        )}
                        {!skill.already_exists && skill.file_count > 1 && (
                          <span className="shrink-0 text-10 text-[var(--theme-text-secondary)]">
                            {t("project.fileCount", {
                              count: skill.file_count,
                            })}
                          </span>
                        )}
                      </div>
                      {skill.description && (
                        <p className="mt-0.5 text-12 text-theme-text-secondary [overflow-wrap:anywhere]">
                          {skill.description}
                        </p>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </EditorSidebar>
  );
}
