import { useState, useMemo } from "react";
import {
  SandpackProvider,
  SandpackLayout,
  SandpackPreview,
  SandpackCodeEditor,
  SandpackFileExplorer,
} from "@codesandbox/sandpack-react";
import { useTranslation } from "react-i18next";
import {
  Play,
  Code2,
  FolderTree,
  ExternalLink,
  Maximize2,
  Minimize2,
  X,
  AlertCircle,
} from "lucide-react";
import { clsx } from "clsx";

// Sandpack 支持的模板类型（精简版）
type SandpackTemplate =
  | "react"
  | "vue"
  | "vanilla"
  | "angular"
  | "svelte"
  | "solid"
  | "node"
  | "nextjs";

// 项目模板映射
const TEMPLATE_MAP: Record<string, SandpackTemplate> = {
  react: "react",
  vue: "vue",
  vanilla: "vanilla",
  static: "vanilla",
};

interface ProjectPreviewProps {
  name: string;
  template: string;
  files: Record<string, string>;
  entry?: string;
  onClose?: () => void;
  showHeader?: boolean;
}

// 自定义布局组件
function CustomLayout({
  showExplorer,
  showEditor,
  showPreview,
}: {
  showExplorer: boolean;
  showEditor: boolean;
  showPreview: boolean;
}) {
  return (
    <SandpackLayout className="!h-full !min-h-[400px]">
      {/* 文件浏览器 */}
      {showExplorer && (
        <SandpackFileExplorer
          className="!w-48 shrink-0"
          autoHiddenFiles={false}
        />
      )}

      {/* 代码编辑器 */}
      {showEditor && (
        <SandpackCodeEditor
          className="flex-1 !min-w-0"
          showTabs
          showLineNumbers
          showInlineErrors
          showRunButton={false}
        />
      )}

      {/* 预览 */}
      {showPreview && (
        <SandpackPreview
          className="flex-1 !min-w-0"
          showNavigator
          showRefreshButton
          showOpenInCodeSandbox={false}
        />
      )}
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
}: ProjectPreviewProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"preview" | "code">("preview");
  const [showExplorer, setShowExplorer] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // 检测并转换文件格式
  const sandpackFiles = useMemo(() => {
    const result: Record<string, string> = {};

    for (const [path, content] of Object.entries(files)) {
      // 确保路径以 / 开头
      const normalizedPath = path.startsWith("/") ? path : `/${path}`;
      result[normalizedPath] = content;
    }

    return result;
  }, [files]);

  // 获取 Sandpack 模板
  const sandpackTemplate = TEMPLATE_MAP[template] || "vanilla";

  // 获取入口文件
  const entryFile = useMemo(() => {
    if (entry) return entry;
    if (sandpackFiles["/index.html"]) return "/index.html";
    if (sandpackFiles["/App.jsx"]) return "/App.jsx";
    if (sandpackFiles["/App.tsx"]) return "/App.tsx";
    if (sandpackFiles["/main.js"]) return "/main.js";
    return Object.keys(sandpackFiles)[0] || "/index.js";
  }, [entry, sandpackFiles]);

  // 文件数量
  const fileCount = Object.keys(sandpackFiles).length;

  if (fileCount === 0) {
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
          ? "fixed inset-0 z-[300]"
          : "h-full min-h-[500px] rounded-xl border border-stone-200 dark:border-stone-700"
      )}
    >
      {/* 工具栏 */}
      {showHeader && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-900 shrink-0">
          {/* 左侧：项目信息 */}
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 text-white">
              <Code2 size={18} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
                {name || t("project.untitled", "未命名项目")}
              </h3>
              <p className="text-xs text-stone-500 dark:text-stone-400">
                {t("project.fileCount", "{{count}} 个文件", { count: fileCount })}
                {template !== "static" && ` · ${template}`}
              </p>
            </div>
          </div>

          {/* 中间：标签切换 */}
          <div className="flex items-center gap-1 bg-stone-100 dark:bg-stone-800 rounded-lg p-1">
            <button
              onClick={() => setActiveTab("preview")}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                activeTab === "preview"
                  ? "bg-white dark:bg-stone-700 text-stone-900 dark:text-stone-100 shadow-sm"
                  : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300"
              )}
            >
              <Play size={14} />
              <span>{t("project.preview", "预览")}</span>
            </button>
            <button
              onClick={() => setActiveTab("code")}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                activeTab === "code"
                  ? "bg-white dark:bg-stone-700 text-stone-900 dark:text-stone-100 shadow-sm"
                  : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300"
              )}
            >
              <Code2 size={14} />
              <span>{t("project.code", "代码")}</span>
            </button>
          </div>

          {/* 右侧：操作按钮 */}
          <div className="flex items-center gap-1">
            {/* 文件浏览器切换 */}
            <button
              onClick={() => setShowExplorer(!showExplorer)}
              className={clsx(
                "p-2 rounded-lg transition-colors",
                showExplorer
                  ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                  : "text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800"
              )}
              title={t("project.toggleExplorer", "切换文件浏览器")}
            >
              <FolderTree size={18} />
            </button>

            {/* 全屏按钮 */}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 rounded-lg text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              title={isFullscreen ? t("project.exitFullscreen") : t("project.fullscreen")}
            >
              {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            </button>

            {/* 关闭按钮 */}
            {onClose && (
              <button
                onClick={onClose}
                className="p-2 rounded-lg text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                title={t("common.close")}
              >
                <X size={18} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Sandpack 区域 */}
      <div className="flex-1 min-h-0">
        <SandpackProvider
          template={sandpackTemplate}
          files={sandpackFiles}
          theme="dark"
          options={{
            activeFile: entryFile,
            classes: {
              "sp-wrapper": "!h-full !flex !flex-col",
              "sp-layout": "!h-full !border-0",
            },
          }}
        >
          <CustomLayout
            showExplorer={showExplorer}
            showEditor={activeTab === "code" || true}
            showPreview={activeTab === "preview" || true}
          />
        </SandpackProvider>
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
  const fileCount = Object.keys(files).length;
  const sandpackTemplate = TEMPLATE_MAP[template] || "vanilla";

  // 获取入口文件
  const entryFile = files["/index.html"]
    ? "/index.html"
    : files["/App.jsx"]
      ? "/App.jsx"
      : Object.keys(files)[0] || "/index.js";

  return (
    <div className="my-2 sm:my-3">
      <div className="border border-stone-200 dark:border-stone-700 rounded-xl overflow-hidden bg-white dark:bg-stone-900">
        {/* 工具栏 */}
        <div className="flex items-center justify-between px-4 py-3 bg-stone-50 dark:bg-stone-800/50 border-b border-stone-200 dark:border-stone-700">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 text-white">
              <Code2 size={16} />
            </div>
            <div>
              <h4 className="text-sm font-medium text-stone-900 dark:text-stone-100">
                {name || t("project.untitled", "未命名项目")}
              </h4>
              <p className="text-xs text-stone-500 dark:text-stone-400">
                {t("project.fileCount", "{{count}} 个文件", { count: fileCount })}
              </p>
            </div>
          </div>

          {onExpand && (
            <button
              onClick={onExpand}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500 hover:bg-blue-600 text-white text-xs font-medium transition-colors"
            >
              <ExternalLink size={14} />
              <span>{t("project.expand", "展开预览")}</span>
            </button>
          )}
        </div>

        {/* 预览区域 */}
        <div className="h-[400px]">
          <SandpackProvider
            template={sandpackTemplate}
            files={files}
            theme="dark"
            options={{
              activeFile: entryFile,
              classes: {
                "sp-wrapper": "!h-full",
                "sp-layout": "!h-full !border-0",
              },
            }}
          >
            <SandpackLayout className="!h-full !min-h-[400px]">
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
