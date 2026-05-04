import { useState } from "react";
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
                const isOpen = Boolean(previewFileContent[filePath]);
                const isLoadingFile = previewFileLoading === filePath;
                const binaryInfo = previewBinaryFiles[filePath];

                return (
                  <div
                    key={filePath}
                    className="overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/78"
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
                      className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-[var(--theme-primary-light)]/80"
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
                          <pre className="max-h-64 overflow-auto p-3 text-xs leading-5 text-[var(--theme-text)] whitespace-pre-wrap break-all font-mono">
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
    </EditorSidebar>
  );
}
