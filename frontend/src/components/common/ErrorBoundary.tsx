import { Component, ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import i18n from "i18next";

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
  }

  render() {
    if (this.state.hasError) {
      const t = i18n.t.bind(i18n);
      return (
        <div className="min-h-screen flex items-center justify-center bg-stone-50 dark:bg-stone-950 px-4">
          <div className="w-full max-w-[380px] sm:max-w-[420px] rounded-2xl border border-stone-200/80 dark:border-stone-800/60 bg-white/80 dark:bg-stone-900/80 p-8 sm:p-10 text-center shadow-[0_2px_12px_rgba(0,0,0,0.04)] dark:shadow-[0_2px_16px_rgba(0,0,0,0.2)]">
            <div className="mx-auto mb-5 w-14 h-14 rounded-full bg-amber-50 dark:bg-amber-500/10 flex items-center justify-center">
              <AlertTriangle className="w-7 h-7 text-amber-500 dark:text-amber-400" />
            </div>
            <h1 className="text-xl font-bold text-stone-900 dark:text-stone-100 font-serif tracking-tight mb-2">
              {t("errorBoundary.title")}
            </h1>
            <p className="text-sm text-stone-500 dark:text-stone-400 leading-relaxed mb-6">
              {this.state.error?.message || t("errorBoundary.unexpectedError")}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl bg-stone-900 dark:bg-stone-100 text-white dark:text-stone-900 text-sm font-medium hover:bg-stone-800 dark:hover:bg-stone-200 transition-colors duration-200"
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
