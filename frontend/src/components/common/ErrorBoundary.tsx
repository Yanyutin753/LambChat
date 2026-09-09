import { Component, ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import clsx from "clsx";
import i18n from "i18next";
import { attemptChunkReload, isChunkLoadError } from "../../utils/chunkLoadRecovery";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
    // 桌面端更新后旧 chunk 404：自动带缓存参数重载自愈，不把裸报错
    // （Failed to fetch dynamically imported module: ...）甩给用户。
    if (isChunkLoadError(error)) {
      attemptChunkReload();
    }
  }

  render() {
    if (this.state.hasError) {
      const t = i18n.t.bind(i18n);
      const isChunkError = isChunkLoadError(this.state.error);
      return (
        <div className="safe-area-viewport-padding min-h-screen flex items-center justify-center bg-stone-50 dark:bg-stone-950 px-4">
          <div className="w-full max-w-[380px] sm:max-w-[420px] rounded-2xl border border-stone-200/80 dark:border-stone-800/60 bg-white/80 dark:bg-stone-900/80 p-8 sm:p-10 text-center shadow-[0_2px_12px_rgba(0,0,0,0.04)] dark:shadow-[0_2px_16px_rgba(0,0,0,0.2)]">
            <div className="mx-auto mb-5 w-14 h-14 rounded-full bg-amber-50 dark:bg-amber-500/10 flex items-center justify-center">
              <AlertTriangle className="w-7 h-7 text-amber-500 dark:text-amber-400" />
            </div>
            <h1 className="text-20 font-bold text-stone-900 dark:text-stone-100 font-serif tracking-tight mb-2">
              {isChunkError
                ? t("errorBoundary.updatingTitle", "正在更新资源")
                : t("errorBoundary.title")}
            </h1>
            <p className="text-14 text-stone-500 dark:text-stone-400 leading-relaxed mb-6 break-words">
              {isChunkError
                ? t(
                    "errorBoundary.updatingMessage",
                    "应用资源已更新，正在自动刷新页面；若没有反应，请点击下方按钮重试。",
                  )
                : this.state.error?.message ||
                  t("errorBoundary.unexpectedError")}
            </p>
            <button
              onClick={() => window.location.reload()}
              className={clsx(
                "inline-flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl",
                "text-14 font-medium text-white",
                "transition-all duration-200 ease-out",
                "hover:shadow-[0_4px_16px_-4px_var(--theme-shadow-color,rgba(0,0,0,0.25))]",
                "active:scale-[0.97]",
                "[&>svg]:transition-transform [&>svg]:duration-300",
                "hover:[&>svg]:-rotate-180",
                "bg-[var(--theme-primary,#1c1917)] dark:bg-[var(--theme-primary,#e7e5e4)]",
                "dark:text-stone-900",
                "hover:brightness-110 dark:hover:brightness-90",
              )}
            >
              <RotateCcw className="w-4 h-4" />
              {t("errorBoundary.reloadPage")}
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
