import { useState, useMemo } from "react";
import {
  SandpackProvider,
  SandpackLayout,
  SandpackPreview,
  SandpackCodeEditor,
  SandpackFileExplorer,
} from "@codesandbox/sandpack-react";
import { useTranslation } from "react-i18next";
import { useTheme } from "../../../contexts/ThemeContext";
import {
  Play,
  Code2,
  FolderTree,
  ExternalLink,
  X,
  AlertCircle,
  Download,
  PanelRight,
} from "lucide-react";
import { clsx } from "clsx";
import { exportProjectZip } from "../../../utils/exportProjectZip";
import { buildSandpackConfig } from "./projectPreviewUtils";
import StackBlitzPreview from "./StackBlitzPreview";

interface ProjectPreviewProps {
  name: string;
  template: string;
  files: Record<string, string>;
  entry?: string;
  onClose?: () => void;
  showHeader?: boolean;
  showTabs?: boolean;
  showFileExplorer?: boolean;
  isFullscreen?: boolean;
  onToggleSidebar?: () => void;
}

// 自定义布局组件
function CustomLayout({
  showExplorer,
  showEditor,
  showPreview,
  isFullscreen,
}: {
  showExplorer: boolean;
  showEditor: boolean;
  showPreview: boolean;
  isFullscreen?: boolean;
}) {
  return (
    <SandpackLayout
      className={clsx("!h-full", isFullscreen ? "!min-h-0" : "!min-h-[400px]")}
    >
      {showExplorer && (
        <SandpackFileExplorer
          className="!w-48 !h-full shrink-0"
          autoHiddenFiles={true}
        />
      )}

      <div
        className={clsx(
          "flex-1 !min-w-0 !h-full overflow-hidden",
          !showEditor && "hidden",
        )}
      >
        <SandpackCodeEditor
          className="!h-full"
          showTabs
          showLineNumbers
          showInlineErrors
          showRunButton={false}
        />
      </div>

      <div
        className={clsx(
          "flex-1 !min-w-0 !h-full overflow-hidden",
          !showPreview && "hidden",
        )}
      >
        <SandpackPreview
          className="!h-full"
          showNavigator
          showRefreshButton
          showOpenInCodeSandbox={false}
        />
      </div>
    </SandpackLayout>
  );
}

export default function ProjectPreview({
  name,
  template,
  files,
  entry,
  onClose,
  showHeader = true,
  showTabs = true,
  showFileExplorer = false,
  isFullscreen: externalFullscreen,
  onToggleSidebar,
}: ProjectPreviewProps) {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const [activeTab, setActiveTab] = useState<"preview" | "code">("preview");
  const [showExplorer, setShowExplorer] = useState(showFileExplorer);
  const isFullscreen = !!externalFullscreen;

  const config = useMemo(
    () => buildSandpackConfig(template, files, entry),
    [template, files, entry],
  );

  // 对 Vue 项目使用 StackBlitz
  const useStackBlitz =
    template === "vue" ||
    config.template === "vue" ||
    config.template === "vue-ts";

  const sandpackInstanceKey = useMemo(
    () =>
      JSON.stringify({
        template: config.template ?? "custom",
        entry: config.customSetup?.entry ?? config.entryFile,
        filePaths: Object.keys(config.files).sort(),
      }),
    [config],
  );

  if (Object.keys(config.files).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <AlertCircle size={32} className="text-amber-500" />
        <p className="text-sm text-stone-500 dark:text-stone-400">
          {t("project.noFiles", "没有可预览的文件")}
        </p>
      </div>
    );
  }

  return (
    <div
      className={clsx(
        "flex flex-col bg-white dark:bg-stone-900 overflow-hidden",
        isFullscreen
          ? "h-full w-full"
          : "h-full min-h-[300px] sm:min-h-[500px] rounded-xl border border-stone-200 dark:border-stone-700",
      )}
    >
      {/* 工具栏 */}
      {showHeader && (
        <div className="flex items-center justify-between px-2 sm:px-4 py-1.5 sm:py-3 border-b border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-900 shrink-0 gap-1 sm:gap-0">
          {/* 左侧：项目信息 */}
          <div className="flex items-center gap-1.5 sm:gap-3 min-w-0 flex-1">
            <div className="p-1 sm:p-2 rounded-md sm:rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 text-white shrink-0">
              <Code2 size={14} className="sm:w-4 sm:h-4" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xs sm:text-sm font-semibold text-stone-900 dark:text-stone-100 truncate">
                {name || t("project.untitled", "未命名项目")}
              </h3>
              <p className="text-xs text-stone-500 dark:text-stone-400 hidden sm:block">
                {t("project.fileCount", "{{count}} 个文件", {
                  count: Object.keys(config.files).length,
                })}
                {config.template &&
                  config.template !== "static" &&
                  ` · ${config.template}`}
              </p>
            </div>
          </div>

          {/* 右侧：标签切换 + 操作按钮 */}
          <div className="flex items-center gap-0.5 sm:gap-1 shrink-0 flex-nowrap">
            {showTabs && (
              <>
                <button
                  onClick={() =>
                    setActiveTab(activeTab === "preview" ? "code" : "preview")
                  }
                  className="sm:hidden flex items-center justify-center w-7 h-7 rounded-md bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-300 transition-colors"
                  title={
                    activeTab === "preview"
                      ? t("project.code", "代码")
                      : t("project.preview", "预览")
                  }
                >
                  {activeTab === "preview" ? (
                    <Code2 size={14} />
                  ) : (
                    <Play size={14} />
                  )}
                </button>

                <div className="hidden sm:flex items-center bg-stone-100 dark:bg-stone-800 rounded-lg p-0.5">
                  <button
                    onClick={() => setActiveTab("preview")}
                    className={clsx(
                      "flex items-center gap-1 px-3 py-1 rounded-md text-xs font-medium transition-colors",
                      activeTab === "preview"
                        ? "bg-white dark:bg-stone-700 text-stone-900 dark:text-stone-100 shadow-sm"
                        : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300",
                    )}
                  >
                    <Play size={14} />
                    {t("project.preview", "预览")}
                  </button>
                  <button
                    onClick={() => setActiveTab("code")}
                    className={clsx(
                      "flex items-center gap-1 px-3 py-1 rounded-md text-xs font-medium transition-colors",
                      activeTab === "code"
                        ? "bg-white dark:bg-stone-700 text-stone-900 dark:text-stone-100 shadow-sm"
                        : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300",
                    )}
                  >
                    <Code2 size={14} />
                    {t("project.code", "代码")}
                  </button>
                </div>
              </>
            )}

            {showFileExplorer && (
              <button
                onClick={() => setShowExplorer(!showExplorer)}
                className={clsx(
                  "p-1 sm:p-1.5 rounded-md sm:rounded-lg transition-colors",
                  showExplorer
                    ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                    : "text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800",
                )}
                title={t("project.toggleExplorer", "切换文件浏览器")}
              >
                <FolderTree size={14} className="sm:w-4 sm:h-4" />
              </button>
            )}

            {isFullscreen && (
              <button
                onClick={() => exportProjectZip(files, name)}
                className="flex items-center gap-1 px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg bg-stone-100 dark:bg-stone-800 hover:bg-stone-200 dark:hover:bg-stone-700 text-stone-600 dark:text-stone-300 text-xs font-medium transition-colors"
              >
                <Download size={14} />
                <span className="hidden sm:inline">
                  {t("project.exportZip")}
                </span>
              </button>
            )}

            {onClose && (
              <button
                onClick={onClose}
                className="p-1 sm:p-1.5 rounded-md sm:rounded-lg text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                title={t("common.close")}
              >
                <X size={14} className="sm:w-4 sm:h-4" />
              </button>
            )}

            {onToggleSidebar && (
              <button
                onClick={onToggleSidebar}
                className="hidden sm:flex items-center justify-center w-7 h-7 rounded-lg text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                title={t("documents.sidebarView", "侧边栏")}
              >
                <PanelRight size={14} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* 预览区域 */}
      <div
        className={clsx(
          "flex-1 min-h-0 h-[200px] sm:h-auto",
          isFullscreen && "h-[calc(100vh-120px)]",
        )}
      >
        {useStackBlitz ? (
          <StackBlitzPreview
            name={name}
            template={template}
            files={files}
            entry={entry}
          />
        ) : (
          <SandpackProvider
            key={sandpackInstanceKey}
            template={config.template}
            customSetup={config.customSetup}
            files={config.files}
            theme={theme}
            options={{
              activeFile: config.entryFile,
              visibleFiles: config.visibleFiles,
              classes: {
                "sp-wrapper": "!h-full !flex !flex-col",
                "sp-layout": "!h-full !border-0",
              },
            }}
          >
            <CustomLayout
              showExplorer={showExplorer}
              showEditor={activeTab === "code"}
              showPreview={activeTab === "preview"}
              isFullscreen={isFullscreen}
            />
          </SandpackProvider>
        )}
      </div>
    </div>
  );
}

// 导出一个简化版本，用于嵌入消息
export function ProjectPreviewCompact({
  name,
  template,
  files,
  onExpand,
}: {
  name: string;
  template: string;
  files: Record<string, string>;
  onExpand?: () => void;
}) {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const config = useMemo(
    () => buildSandpackConfig(template, files),
    [template, files],
  );
  const sandpackInstanceKey = useMemo(
    () =>
      JSON.stringify({
        template: config.template ?? "custom",
        entry: config.customSetup?.entry ?? config.entryFile,
        filePaths: Object.keys(config.files).sort(),
      }),
    [config],
  );

  return (
    <div className="my-2 sm:my-3">
      <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden bg-white dark:bg-stone-900">
        {/* 工具栏 */}
        <div className="flex items-center justify-between px-2 sm:px-4 py-2 sm:py-3 bg-stone-50 dark:bg-stone-800/50 border-b border-stone-200 dark:border-stone-700 gap-2">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <div className="p-1.5 sm:p-2 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 text-white shrink-0">
              <Code2 size={16} />
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate max-w-[100px] sm:max-w-none">
                {name || t("project.untitled", "未命名项目")}
              </h4>
              <p className="text-xs text-stone-500 dark:text-stone-400 hidden sm:block">
                {t("project.fileCount", "{{count}} 个文件", {
                  count: Object.keys(config.files).length,
                })}
                {config.template &&
                  config.template !== "static" &&
                  ` · ${config.template}`}
              </p>
            </div>
          </div>

          {onExpand && (
            <button
              onClick={onExpand}
              className="flex items-center gap-1 px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg bg-blue-500 hover:bg-blue-600 text-white text-xs font-medium transition-colors shrink-0"
            >
              <ExternalLink size={14} />
              <span className="hidden sm:inline">
                {t("project.expand", "展开预览")}
              </span>
            </button>
          )}
        </div>

        {/* 预览区域 */}
        <div className="h-[250px] sm:h-[400px]">
          <SandpackProvider
            key={sandpackInstanceKey}
            template={config.template}
            customSetup={config.customSetup}
            files={config.files}
            theme={theme}
            options={{
              activeFile: config.entryFile,
              visibleFiles: config.visibleFiles,
              classes: {
                "sp-wrapper": "!h-full",
                "sp-layout": "!h-full !border-0",
              },
            }}
          >
            <SandpackLayout className="!h-full !min-h-[250px] sm:!min-h-[400px]">
              <SandpackPreview
                className="flex-1"
                showNavigator
                showRefreshButton
                showOpenInCodeSandbox={false}
              />
            </SandpackLayout>
          </SandpackProvider>
        </div>
      </div>
    </div>
  );
}
