import { DialogCloseButton } from "../../common/DialogCloseButton";
import { ModalSurface } from "../../common/ModalSurface";
import { useState, useRef } from "react";

import {
  FileText,
  ShoppingBag,
  ChevronRight,
  ChevronDown,
  Loader2 as Loader2Icon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { EditorSidebar } from "../../common/EditorSidebar";
import { BinaryFilePreview } from "../../skill/BinaryFilePreview";
import { SkillEditor } from "../../skill/SkillEditor";
import { SkillFileLoadState } from "../../skill/SkillFileLoadState";
import { Button } from "../../common";
import { ConfigPanelErrorCallout } from "../ConfigPanelErrorCallout";
import type {
  MarketplaceSkillResponse,
  MarketplaceSkillFilesResponse,
} from "../../../types";

interface SkillPreviewModalProps {
  previewSkill: MarketplaceSkillResponse;
  previewFiles: MarketplaceSkillFilesResponse | null;
  previewLoading: boolean;
  previewError?: string;
  previewFileErrors: Record<string, string>;
  previewFileContent: Record<string, string>;
  previewBinaryFiles: Record<
    string,
    { url: string; mime_type: string; size: number }
  >;
  previewFileLoading: ReadonlySet<string>;
  onClose: () => void;
  onReadFile: (skillName: string, filePath: string) => void;
  onRetryFiles: () => void;
}

export function SkillPreviewModal({
  previewSkill,
  previewFiles,
  previewLoading,
  previewError,
  previewFileErrors,
  previewFileContent,
  previewBinaryFiles,
  previewFileLoading,
  onClose,
  onReadFile,
  onRetryFiles,
}: SkillPreviewModalProps) {
  const { t } = useTranslation();
  const [isDescExpanded, setIsDescExpanded] = useState(false);
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const hasLongDescription = (previewSkill.description?.length || 0) > 80;

  const previewBinaryInfo = previewFilePath
    ? previewBinaryFiles[previewFilePath]
    : undefined;
  const previewTextContent = previewFilePath
    ? previewFileContent[previewFilePath]
    : undefined;
  const isPreviewLoading =
    !!previewFilePath &&
    previewFileLoading.has(previewFilePath) &&
    previewTextContent === undefined &&
    !previewBinaryInfo;

  return (
    <>
      <EditorSidebar
        open={true}
        onClose={onClose}
        title={previewSkill.skill_name}
        icon={<ShoppingBag size={16} />}
        width="wide"
      >
        <div ref={listRef} tabIndex={-1} className="es-form">
          <div className="space-y-2">
            <span className="font-mono text-12 text-[var(--theme-text-secondary)]">
              v{previewSkill.version}
            </span>
            <p
              className={`text-13 leading-relaxed text-[var(--theme-text-secondary)] ${
                hasLongDescription && !isDescExpanded ? "line-clamp-3" : ""
              }`}
            >
              {previewSkill.description || t("marketplace.noDescription")}
            </p>
            {hasLongDescription && (
              <button
                type="button"
                aria-expanded={isDescExpanded}
                onClick={() => setIsDescExpanded((value) => !value)}
                className="inline-flex min-h-11 items-center gap-1 text-12 text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)]"
              >
                {isDescExpanded
                  ? t("marketplace.previewCollapse")
                  : t("marketplace.previewExpand")}
                <ChevronDown
                  size={14}
                  className={isDescExpanded ? "rotate-180" : ""}
                />
              </button>
            )}
          </div>
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
            <div className="flex items-center gap-2 text-14 text-[var(--theme-text-secondary)]">
              <LoadingSpinner size="sm" />
              <span>{t("marketplace.loadingFiles")}</span>
            </div>
          ) : previewError ? (
            <div className="flex flex-col items-start gap-3">
              <ConfigPanelErrorCallout message={previewError} />
              <Button
                size="lg"
                onClick={() => {
                  listRef.current?.focus();
                  onRetryFiles();
                }}
              >
                {t("common.retry")}
              </Button>
            </div>
          ) : previewFiles?.files.length ? (
            <div>
              <h3 className="mb-3 flex items-center gap-2 text-13 font-medium font-sans text-[var(--theme-text)]">
                <FileText size={16} className="text-[var(--theme-primary)]" />
                {t("marketplace.skillFiles")} ({previewFiles.files.length})
              </h3>
              <div className="space-y-2">
                {previewFiles.files.map((filePath) => {
                  const isLoaded = Boolean(
                    previewFileContent[filePath] !== undefined ||
                      previewBinaryFiles[filePath],
                  );
                  const isLoadingFile = previewFileLoading.has(filePath);

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
                          <div className="truncate text-12 font-medium text-[var(--theme-text)]">
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
            <p className="text-14 text-[var(--theme-text-secondary)]">
              {t("marketplace.noFiles")}
            </p>
          )}
        </div>
      </EditorSidebar>

      {previewFilePath && (
        <ModalSurface
          layer={1200}
          className="modal-wide"
          open
          label={previewFilePath}
          onClose={() => setPreviewFilePath(null)}
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
                <div className="truncate text-14 font-medium text-[var(--theme-text)]">
                  {previewFilePath}
                </div>
              </div>
              <DialogCloseButton
                aria-label={t("marketplace.closePreview")}
                title={t("marketplace.closePreview")}
                onClick={() => setPreviewFilePath(null)}
              />
            </div>

            <div
              ref={contentRef}
              tabIndex={-1}
              className="min-h-0 flex-1 overflow-hidden bg-[var(--theme-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--theme-primary)]/50"
            >
              {isPreviewLoading || previewFileErrors[previewFilePath] ? (
                <SkillFileLoadState
                  path={previewFilePath}
                  error={previewFileErrors[previewFilePath]}
                  onRetry={() => {
                    contentRef.current?.focus();
                    onReadFile(previewSkill.skill_name, previewFilePath);
                  }}
                />
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
        </ModalSurface>
      )}
    </>
  );
}
