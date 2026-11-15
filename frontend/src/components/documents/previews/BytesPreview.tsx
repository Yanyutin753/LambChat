import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fetchUploadFile } from "../documentFetchCache";
import { decodePreviewText, formatHexPreview } from "../utils/fileBytesPreview";
import { downloadUrl } from "../../common/viewerDownload";
import { Loading } from "../../common/LoadingSpinner";
import { Button } from "../../common/ui/Button";
import { getAccessToken } from "../../../services/api/token";
import { isCurrentFileAccount } from "../../../services/api/uploadFileUrl";

const PREVIEW_BYTES = 64 * 1024;

export default function BytesPreview({
  url,
  fileName,
  content,
}: {
  url?: string | null;
  fileName: string;
  content?: string;
}) {
  const { t } = useTranslation();
  const [result, setResult] = useState<{
    text: string;
    binary: boolean;
    truncated: boolean;
  }>();
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const account = getAccessToken();
    setResult(undefined);
    setError(false);
    if (!url) {
      setResult({
        text: content?.slice(0, PREVIEW_BYTES) || "",
        binary: false,
        truncated: (content?.length || 0) > PREVIEW_BYTES,
      });
      return () => controller.abort();
    }
    void (async () => {
      const response = await fetchUploadFile(url, {
        signal: controller.signal,
      });
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");
      const bytes = new Uint8Array(PREVIEW_BYTES + 1);
      let size = 0;
      try {
        while (size < bytes.length) {
          const { value, done } = await reader.read();
          if (done) break;
          const chunk = value.subarray(0, bytes.length - size);
          bytes.set(chunk, size);
          size += chunk.length;
        }
      } finally {
        await reader.cancel();
      }
      if (controller.signal.aborted || !isCurrentFileAccount(account)) return;
      const truncated = size > PREVIEW_BYTES;
      const preview = bytes.subarray(0, Math.min(size, PREVIEW_BYTES));
      const charset = /charset=["']?([^;\s"']+)/i.exec(
        response.headers.get("content-type") || "",
      )?.[1];
      const text = decodePreviewText(preview, charset, truncated);
      setResult({
        text: text ?? formatHexPreview(preview),
        binary: text === null,
        truncated,
      });
    })().catch(() => {
      if (!controller.signal.aborted) setError(true);
    });
    return () => controller.abort();
  }, [url, content, retry]);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-theme-border px-4 py-3 text-12 text-theme-text-secondary">
        <span>
          {t(result?.binary ? "documents.hexPreview" : "documents.textPreview")}
          {result?.truncated ? ` · ${t("documents.previewBytesLimit")}` : ""}
        </span>
        {url && (
          <Button
            loading={saving}
            onClick={async () => {
              setSaving(true);
              try {
                await downloadUrl(url, fileName);
              } finally {
                setSaving(false);
              }
            }}
          >
            {t("documents.downloadFile")}
          </Button>
        )}
      </div>
      {error ? (
        <div role="alert" className="p-4 text-theme-error">
          <p>{t("documents.unableToLoadContent")}</p>
          <Button onClick={() => setRetry((value) => value + 1)}>
            {t("common.retry")}
          </Button>
        </div>
      ) : !result ? (
        <Loading className="p-4" />
      ) : (
        <pre
          tabIndex={0}
          className="min-h-0 flex-1 overflow-auto whitespace-pre p-4 font-mono text-12 leading-relaxed text-theme-text"
        >
          {result.text}
        </pre>
      )}
    </div>
  );
}
