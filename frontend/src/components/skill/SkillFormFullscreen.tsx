import { useTranslation } from "react-i18next";
import { Shrink, Plus, ChevronDown, Upload, Search } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useCodeMirrorReady } from "../../hooks/useCodeMirrorReady";
import { FileTreeItem } from "./FileTreeItem";
import { FileTabs } from "./FileTabs";
import { SkillEditor } from "./SkillEditor";
import { BinaryFilePreview } from "./BinaryFilePreview";
import { SkillFileLoadState } from "./SkillFileLoadState";
import { buildFileTree } from "./SkillForm.utils";
import { Input, ToolbarIconButton } from "../common";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import type { SkillFormActions } from "./SkillForm.types";

export function SkillFormFullscreen(a: SkillFormActions) {
  const { t } = useTranslation();
  const editorRef = useRef<HTMLDivElement>(null);
  const [naming, setNaming] = useState(false);
  const errorId = useId();
  const currentPath = a.files[a.activeFileIndex]?.path || "";
  const searchReady = useCodeMirrorReady(
    editorRef,
    !a.loadingFilePath && !a.fileLoadError && !a.binaryFiles[currentPath],
  );
  const addFile = () => {
    setNaming(true);
    a.addFile();
  };
  const handleSearch = () => {
    const editor = editorRef.current?.querySelector<HTMLElement>(".cm-editor");
    if (!editor) return;
    void import("../common/codeMirrorSearchExtensions").then(
      ({ openCodeMirrorSearch }) => openCodeMirrorSearch(editor),
    );
  };

  return (
    <>
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Editor area — sidebar + editor, full-screen focused */}
        <div className="skill-form-editor flex flex-1 min-w-0 min-h-0 overflow-hidden">
          {/* Desktop sidebar */}
          <div className="skill-file-sidebar hidden w-52 shrink-0 flex-col sm:flex lg:w-60">
            <div className="flex items-center justify-between px-3 py-1.5">
              <div className="flex items-center gap-1 text-11 font-semibold uppercase tracking-[0.18em] text-[var(--theme-text-secondary)]/80 select-none">
                <ChevronDown size={12} />
                {t("skills.form.files", "Files")}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto py-0.5">
              {buildFileTree(a.files).map((node, i) => (
                <FileTreeItem
                  key={i}
                  node={node}
                  depth={0}
                  activeFileIndex={a.activeFileIndex}
                  onSelect={a.setActiveFileIndex}
                  onRemove={a.removeFile}
                  canRemove={a.files.length > 1}
                />
              ))}
            </div>
            <div className="shrink-0 px-2 py-1.5 space-y-1">
              <button
                type="button"
                onClick={addFile}
                className="w-full flex items-center gap-1.5 rounded-xl px-2 py-1.5 text-14 text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-white/5 transition-colors"
              >
                <Plus size={13} />
                {t("skills.form.addFile")}
              </button>
              {a.allowBinaryUploads && (
                <button
                  type="button"
                  onClick={a.addBinaryFile}
                  className="w-full flex items-center gap-1.5 rounded-xl px-2 py-1.5 text-14 text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-white/5 transition-colors"
                >
                  <Upload size={13} />
                  {t("skills.form.addBinaryFile", "Upload binary file")}
                </button>
              )}
            </div>
          </div>

          {/* Right: editor only */}
          <div ref={editorRef} className="flex flex-1 flex-col min-w-0 min-h-0">
            {/* Mobile header: tabs + actions */}
            <div className="shrink-0 flex items-center gap-1 px-3 py-2">
              {naming || !currentPath.trim() ? (
                <Input
                  type="text"
                  data-skill-file-path
                  aria-label={t("skills.form.filePath")}
                  aria-describedby={a.errors.files ? errorId : undefined}
                  placeholder={t("skills.form.fileNamePlaceholder")}
                  value={currentPath}
                  disabled={!a.isCurrentFileLoaded}
                  error={!!a.errors.files}
                  className="min-w-0 flex-1 font-mono"
                  onChange={(event) =>
                    a.updateFilePath(a.activeFileIndex, event.target.value)
                  }
                  onBlur={() => setNaming(false)}
                  onKeyDown={(event) => {
                    if (
                      event.key !== "Enter" ||
                      event.nativeEvent.isComposing ||
                      event.keyCode === 229
                    )
                      return;
                    event.preventDefault();
                    if (currentPath.trim() && !a.errors.files) {
                      setNaming(false);
                      editorRef.current
                        ?.querySelector<HTMLElement>(".cm-content")
                        ?.focus();
                    }
                  }}
                />
              ) : (
                <>
                  <p
                    className="hidden min-w-0 flex-1 truncate font-mono text-12 text-[var(--theme-text-secondary)] sm:block"
                    title={a.files[a.activeFileIndex]?.path}
                  >
                    {a.files[a.activeFileIndex]?.path ||
                      t("skills.form.untitled")}
                  </p>
                  <div className="flex-1 min-w-0 sm:hidden">
                    <FileTabs
                      files={a.files}
                      activeFileIndex={a.activeFileIndex}
                      onSelect={a.setActiveFileIndex}
                      onRemove={a.removeFile}
                      untitledLabel={t("skills.form.untitled")}
                    />
                  </div>
                </>
              )}
              <ToolbarIconButton
                onClick={addFile}
                icon={<Plus size={15} />}
                aria-label={t("skills.form.addFile")}
                title={t("skills.form.addFile")}
                className="sm:hidden"
              />
              {a.allowBinaryUploads && (
                <ToolbarIconButton
                  onClick={a.addBinaryFile}
                  icon={<Upload size={15} />}
                  aria-label={t("skills.form.addBinaryFile")}
                  title={t("skills.form.addBinaryFile")}
                  className="sm:hidden"
                />
              )}
              <ToolbarIconButton
                onClick={handleSearch}
                disabled={!searchReady}
                icon={<Search size={15} />}
                aria-label={t("common.search")}
                title={t("common.search")}
              />
              <ToolbarIconButton
                onClick={() => a.toggleFullscreen(false)}
                icon={<Shrink size={18} />}
                aria-label={t("skills.form.exitFullscreen")}
                title={t("skills.form.exitFullscreen")}
              />
            </div>
            {a.errors.files && (
              <div id={errorId} className="mx-3">
                <ConfigPanelErrorCallout message={a.errors.files} />
              </div>
            )}

            {/* Editor / Binary Preview */}
            <div className="flex-1 min-h-0 p-3 sm:p-4">
              {(() => {
                const currentPath = a.files[a.activeFileIndex]?.path || "";
                const binaryInfo = a.binaryFiles?.[currentPath];

                if (a.loadingFilePath === currentPath || a.fileLoadError) {
                  return (
                    <SkillFileLoadState
                      path={currentPath}
                      error={a.fileLoadError}
                      onRetry={() => a.loadFileContent(a.activeFileIndex)}
                    />
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
                    className={`flex h-full flex-col overflow-hidden rounded-2xl bg-[var(--theme-bg-subtle)] transition-colors duration-150 ${
                      a.errors.content
                        ? "ring-1 ring-red-300 dark:ring-red-700"
                        : ""
                    } skill-editor-shell`}
                  >
                    <SkillEditor
                      value={a.files[a.activeFileIndex]?.content || ""}
                      onChange={(val) =>
                        a.updateFileContent(a.activeFileIndex, val)
                      }
                      className="flex-1 min-h-0 code-editor--overlay-search"
                      showToolbar={false}
                      filePath={a.files[a.activeFileIndex]?.path}
                      readOnly={a.isLoading}
                    />
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
