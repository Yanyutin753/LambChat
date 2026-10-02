/**
 * SharedEntry - 公开分享页统一入口
 *
 * 拉取一次分享内容，按 share_scope 分发到会话页或项目页，
 * 并把已拉取的数据作为 initialData 注入，避免子组件重复请求。
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { shareApi } from "../../services/api/share";
import type { SharedContent } from "../../types";
import { SharedPage } from "./SharedPage";
import { SharedProjectPage } from "./SharedProjectPage";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { SceneIllustration } from "../common/SceneIllustration";
import { Button } from "../common/ui/Button";

export function SharedEntry() {
  const { shareId } = useParams<{ shareId: string }>();
  return <SharedContentLoader key={shareId} shareId={shareId} />;
}

function SharedContentLoader({ shareId }: { shareId: string | undefined }) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<SharedContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<
    "auth_required" | "not_found" | "load_failed" | null
  >(null);
  const [retryKey, setRetryKey] = useState(0);

  // Public routes must scroll even before a session or project has loaded.
  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => document.documentElement.classList.remove("allow-scroll");
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!shareId) {
        setError("not_found");
        setLoading(false);
        return;
      }
      try {
        const res = await shareApi.getSharedContent(shareId);
        if (!cancelled) setData(res);
      } catch (failure) {
        if (cancelled) return;
        const status =
          failure && typeof failure === "object" && "status" in failure
            ? failure.status
            : undefined;
        setError(
          status === 401
            ? "auth_required"
            : status === 404
              ? "not_found"
              : "load_failed",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [shareId, retryKey]);

  useLayoutEffect(() => {
    // Session success retains SharedPage's existing fade; errors and projects
    // must also replace the server-rendered preview rather than stack below it.
    if (error || (data && "sessions" in data))
      document.getElementById("shared-server-preview")?.remove();
  }, [error, data]);

  return (
    <div ref={rootRef} tabIndex={-1} data-shared-entry className="outline-none">
      {loading || error ? (
        <main className="min-h-dvh bg-theme-bg text-theme-text flex items-center justify-center px-4 py-8">
          {loading ? (
            <div
              role="status"
              className="flex flex-col items-center gap-3 text-14 text-theme-text-secondary"
            >
              <LoadingSpinner size="lg" />
              <span>{t("common.loading")}</span>
            </div>
          ) : (
            <div role="alert" className="w-full max-w-md text-center">
              <SceneIllustration scene="message" className="mx-auto mb-4" />
              <h1 className="font-serif text-20 font-semibold text-theme-text [overflow-wrap:anywhere]">
                {t(
                  error === "auth_required"
                    ? "share.loginRequired"
                    : error === "not_found"
                      ? "share.notFound"
                      : "share.loadFailed",
                )}
              </h1>
              {error !== "load_failed" && (
                <p className="mt-2 text-14 text-theme-text-secondary [overflow-wrap:anywhere]">
                  {t(
                    error === "auth_required"
                      ? "share.loginRequiredDesc"
                      : "share.notFoundDesc",
                  )}
                </p>
              )}
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {error === "load_failed" && (
                  <Button
                    size="lg"
                    variant="primary"
                    onClick={() => {
                      rootRef.current?.focus({ preventScroll: true });
                      setError(null);
                      setLoading(true);
                      setRetryKey((key) => key + 1);
                    }}
                  >
                    {t("common.retry")}
                  </Button>
                )}
                {error === "auth_required" && (
                  <Link
                    to="/auth/login"
                    className="ui-button ui-button--primary ui-button--lg"
                  >
                    {t("auth.loginNow")}
                  </Link>
                )}
                <Link
                  to="/"
                  className="ui-button ui-button--secondary ui-button--lg"
                >
                  {t("errors.backToHome")}
                </Link>
              </div>
            </div>
          )}
        </main>
      ) : data && "sessions" in data ? (
        <SharedProjectPage initialManifest={data} />
      ) : data ? (
        <SharedPage initialData={data} />
      ) : null}
    </div>
  );
}
