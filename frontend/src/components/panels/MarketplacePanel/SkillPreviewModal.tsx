import { useState } from "react";
import { createPortal } from "react-dom";
import {
  FileText,
  ShoppingBag,
  ChevronRight,
  ChevronDown,
  Loader2 as Loader2Icon,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { EditorSidebar } from "../../common/EditorSidebar";
import { BinaryFilePreview } from "../../skill/BinaryFilePreview";
import { SkillEditor } from "../../skill/SkillEditor";
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
}: SkillPreviewModalProps) {
  const { t } = useTranslation();
  const [isDescExpanded, setIsDescExpanded] = useState(false);
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null);

  const previewBinaryInfo = previewFilePath
    ? previewBinaryFiles[previewFilePath]
    : undefined;
  const previewTextContent = previewFilePath
    ? previewFileContent[previewFilePath]
    : undefined;
  const isPreviewLoading =
    !!previewFilePath &&
    previewFileLoading === previewFilePath &&
    !previewTextContent &&
    !previewBinaryInfo;

  return (
    <>
      <EditorSidebar
        open={true}
        onClose={onClose}
        title={previewSkill.skill_name}
        subtitle={
          <span className="inline-flex items-center gap-1.5">
            <span className="skill-meta-pill text-[10px] sm:text-xs">
              v{previewSkill.version}
            </span>
            <button
              type="button"
              onClick={() => setIsDescExpanded((v) => !v)}
              className="text-left text-[11px] leading-relaxed text-[var(--theme-text-secondary)]"
            >
              <span className={!isDescExpanded ? "line-clamp-1" : ""}>
                {previewSkill.description || t("marketplace.noDescription")}
              </span>
              {(previewSkill.description?.length || 0) > 80 && (
                <span className="ml-1 inline-flex items-center gap-0.5 text-[10px] text-[var(--theme-primary)]">
                  {isDescExpanded
                    ? t("marketplace.previewCollapse")
                    : t("marketplace.previewExpand")}
                  <ChevronDown
                    size={10}
                    className={`transition-transform ${
                      isDescExpanded ? "rotate-180" : ""
                    }`}
                  />
                </span>
              )}
            </button>
          </span>
        }
        icon={<ShoppingBag size={16} />}
        width="wide"
      >
        <div className="es-form">
          {/* Tags */}
          {previewSkill.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {previewSkill.tags.slice(0, 5).map((tag) => (
                <span key={tag} className="es-chip">
                  {tag}
                </span>
              ))}
              {previewSkill.tags.length > 5 && (
                <span className="es-chip">+{previewSkill.tags.length - 5}</span>
              )}
            </div>
          )}

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
              <div className="space-y-2">
                {previewFiles.files.map((filePath) => {
                  const isLoaded = Boolean(
                    previewFileContent[filePath] ||
                      previewBinaryFiles[filePath],
                  );
                  const isLoadingFile = previewFileLoading === filePath;

                  return (
                    <div
                      key={filePath}
                      className="overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/78"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setPreviewFilePath(filePath);
                          if (!isLoaded && !isLoadingFile) {
                            onReadFile(previewSkill.skill_name, filePath);
                          }
                        }}
                        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-[var(--theme-bg-subtle)]"
                      >
                        <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                          <FileText size={12} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-xs font-medium text-[var(--theme-text)]">
                            {filePath}
                          </div>
                        </div>
                        {isLoadingFile ? (
                          <Loader2Icon
                            size={14}
                            className="animate-spin text-[var(--theme-text-secondary)]"
                          />
                        ) : (
                          <ChevronRight
                            size={14}
                            className="text-[var(--theme-text-secondary)]"
                          />
                        )}
                      </button>
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
      </EditorSidebar>

      {previewFilePath &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/45 p-3 sm:p-6"
            onClick={() => setPreviewFilePath(null)}
          >
            <div
              className="flex h-[min(84dvh,880px)] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-[0_24px_80px_-32px_rgba(0,0,0,0.55)]"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex min-h-0 items-center gap-2.5 border-b border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-3 py-2 sm:px-4">
                <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                  <FileText size={13} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-[var(--theme-text)]">
                    {previewFilePath}
                  </div>
                </div>
                <button
                  type="button"
                  aria-label={t("marketplace.closePreview")}
                  title={t("marketplace.closePreview")}
                  onClick={() => setPreviewFilePath(null)}
                  className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-[var(--theme-text-secondary)] transition-colors hover:bg-[var(--theme-bg-subtle)] hover:text-[var(--theme-text)]"
                >
                  <X size={15} />
                </button>
              </div>

              <div className="min-h-0 flex-1 overflow-hidden bg-[var(--theme-bg)]">
                {isPreviewLoading ? (
                  <div className="flex h-full items-center justify-center gap-2 text-sm text-[var(--theme-text-secondary)]">
                    <LoadingSpinner size="sm" />
                    <span>{t("marketplace.loadingFiles")}</span>
                  </div>
                ) : previewBinaryInfo ? (
                  <BinaryFilePreview
                    url={previewBinaryInfo.url}
                    mime_type={previewBinaryInfo.mime_type}
                    size={previewBinaryInfo.size}
                    fileName={previewFilePath}
                  />
                ) : (
                  <SkillEditor
                    value={previewTextContent ?? ""}
                    onChange={() => undefined}
                    filePath={previewFilePath}
                    readOnly
                    lineWrapping={false}
                    className="flex-1 min-h-0"
                  />
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
