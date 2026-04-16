import { useState } from "react";
import {
  X,
  FileText,
  ShoppingBag,
  ChevronRight,
  ChevronDown,
  Loader2 as Loader2Icon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { BinaryFilePreview } from "../../skill/BinaryFilePreview";
import type {
  MarketplaceSkillResponse,
  MarketplaceSkillFilesResponse,
} from "../../../types";

interface SkillPreviewModalProps {
  previewSkill: MarketplaceSkillResponse;
  previewFiles: MarketplaceSkillFilesResponse | null;
  previewLoading: boolean;
  previewFileContent: Record<string, string>;
  previewBinaryFiles: Record<
    string,
    { url: string; mime_type: string; size: number }
  >;
  previewFileLoading: string | null;
  onClose: () => void;
  onReadFile: (skillName: string, filePath: string) => void;
  onSetFileContent: React.Dispatch<
    React.SetStateAction<Record<string, string>>
  >;
}

export function SkillPreviewModal({
  previewSkill,
  previewFiles,
  previewLoading,
  previewFileContent,
  previewBinaryFiles,
  previewFileLoading,
  onClose,
  onReadFile,
  onSetFileContent,
}: SkillPreviewModalProps) {
  const { t } = useTranslation();
  const [isDescExpanded, setIsDescExpanded] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 p-0 sm:items-center sm:p-4">
      <div className="skill-preview-shell flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-[1.5rem] border sm:max-h-[88vh] sm:max-w-4xl sm:rounded-[1.75rem] shadow-[0_-16px_48px_-16px_rgba(15,23,42,0.3)] sm:shadow-[0_32px_80px_-32px_rgba(15,23,42,0.55)]">
        {/* Modal Header */}
        <div className="border-b border-[var(--theme-border)] bg-[var(--theme-bg)]/88 px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-[var(--theme-primary-light)] text-[var(--theme-primary)] shadow-sm sm:h-11 sm:w-11 sm:rounded-2xl">
                  <ShoppingBag size={16} className="sm:size-[20px]" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                    <h2 className="truncate text-base font-semibold text-[var(--theme-text)] sm:text-lg">
                      {previewSkill.skill_name}
                    </h2>
                    <span className="skill-meta-pill text-[10px] sm:text-xs">
                      v{previewSkill.version}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsDescExpanded((v) => !v)}
                    className="mt-1 text-left text-sm leading-relaxed text-[var(--theme-text-secondary)]"
                  >
                    <span className={!isDescExpanded ? "line-clamp-2" : ""}>
                      {previewSkill.description ||
                        t("marketplace.noDescription")}
                    </span>
                    {(previewSkill.description?.length || 0) > 80 && (
                      <span className="ml-1 inline-flex items-center gap-0.5 text-xs text-[var(--theme-primary)]">
                        {isDescExpanded
                          ? t("marketplace.previewCollapse")
                          : t("marketplace.previewExpand")}
                        <ChevronDown
                          size={12}
                          className={`transition-transform ${
                            isDescExpanded ? "rotate-180" : ""
                          }`}
                        />
                      </span>
                    )}
                  </button>
                </div>
              </div>
              {previewSkill.tags.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5 sm:mt-4 sm:gap-2">
                  {previewSkill.tags.slice(0, 3).map((tag) => (
                    <span
                      key={tag}
                      className="skill-tag-chip skill-tag-chip--active text-[10px] sm:text-xs"
                    >
                      {tag}
                    </span>
                  ))}
                  {previewSkill.tags.length > 3 && (
                    <span className="skill-tag-chip text-[10px] sm:text-xs">
                      +{previewSkill.tags.length - 3}
                    </span>
                  )}
                </div>
              )}
            </div>
            <button
              onClick={onClose}
              className="btn-icon -mr-1 -mt-1 hover:bg-[var(--theme-bg-card)]"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="skill-modal-body flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5">
          {/* Files */}
          {previewLoading ? (
            <div className="flex items-center gap-2 text-sm text-[var(--theme-text-secondary)]">
              <LoadingSpinner size="sm" />
              <span>{t("marketplace.loadingFiles")}</span>
            </div>
          ) : previewFiles ? (
            <div>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--theme-text)]">
                <FileText size={16} className="text-[var(--theme-primary)]" />
                {t("marketplace.skillFiles")} ({previewFiles.files.length})
              </h3>
              <div className="space-y-3">
                {previewFiles.files.map((filePath) => {
                  const isOpen = Boolean(previewFileContent[filePath]);
                  const isLoadingFile = previewFileLoading === filePath;
                  const binaryInfo = previewBinaryFiles[filePath];

                  return (
                    <div
                      key={filePath}
                      className="overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/78 shadow-sm"
                    >
                      <button
                        onClick={() => {
                          if (isOpen) {
                            onSetFileContent((prev) => {
                              const next = { ...prev };
                              delete next[filePath];
                              return next;
                            });
                            return;
                          }
                          onReadFile(previewSkill.skill_name, filePath);
                        }}
                        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--theme-primary-light)]/80"
                      >
                        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                          <FileText size={14} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-[var(--theme-text)]">
                            {filePath}
                          </div>
                          <div className="text-xs text-[var(--theme-text-secondary)]">
                            {isOpen
                              ? t("marketplace.previewCollapse")
                              : t("marketplace.previewExpand")}
                          </div>
                        </div>
                        {isLoadingFile ? (
                          <Loader2Icon
                            size={16}
                            className="animate-spin text-[var(--theme-text-secondary)]"
                          />
                        ) : (
                          <ChevronRight
                            size={16}
                            className={`text-[var(--theme-text-secondary)] transition-transform ${
                              isOpen ? "rotate-90" : ""
                            }`}
                          />
                        )}
                      </button>
                      {isOpen && (
                        <div className="border-t border-[var(--theme-border)]/60">
                          {binaryInfo ? (
                            <BinaryFilePreview
                              url={binaryInfo.url}
                              mime_type={binaryInfo.mime_type}
                              size={binaryInfo.size}
                              fileName={filePath}
                            />
                          ) : (
                            <pre className="max-h-72 overflow-auto p-4 text-xs leading-6 text-[var(--theme-text)] whitespace-pre-wrap break-all font-mono">
                              {previewFileContent[filePath]}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="text-sm text-[var(--theme-text-secondary)]">
              {t("marketplace.noFiles")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
