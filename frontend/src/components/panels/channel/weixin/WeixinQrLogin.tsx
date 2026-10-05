import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import QRCode from "qrcode";
import { QrCode } from "lucide-react";
import { Button, LoadingSpinner } from "../../../common";
import { ImageWithSkeleton } from "../../../chat/ChatMessage/ImageWithSkeleton";
import { channelApi } from "../../../../services/api/channel";

type QrPhase = "idle" | "loading" | "pending" | "scanned" | "expired" | "error";

/** 轮询连续失败上限（约 3s×N），超限按过期处理 */
const MAX_POLL_FAILURES = 10;

/** 微信 iLink 扫码登录：本地渲染二维码并轮询状态，成功后回填 bot_token */
export function WeixinQrLogin({
  onToken,
}: {
  onToken: (token: string) => void;
}) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<QrPhase>("idle");
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  const renderQr = useCallback(async (qrContent: string) => {
    // qrUrl 是二维码内容字符串（zcode 同款用法），本地编码渲染而非外链图片
    try {
      const dataUrl = await QRCode.toDataURL(qrContent, {
        errorCorrectionLevel: "M",
        margin: 1,
        width: 220,
        color: { dark: "#111827", light: "#ffffff" },
      });
      if (aliveRef.current) setQrDataUrl(dataUrl);
    } catch {
      if (aliveRef.current) setQrDataUrl(null);
    }
  }, []);

  const schedulePoll = useCallback(
    (qrCode: string, intervalMs: number, failures = 0) => {
      pollTimer.current = setTimeout(async () => {
        if (!aliveRef.current) return;
        try {
          const result = await channelApi.pollWeixinRegistration(qrCode);
          if (!aliveRef.current) return;
          if (result.status === "success" && result.bot_token) {
            setPhase("idle");
            setQrDataUrl(null);
            onToken(result.bot_token);
            return;
          }
          if (result.status === "expired" || result.status === "error") {
            setPhase(result.status);
            setErrorMessage(result.message ?? null);
            return;
          }
          if (result.status === "scanned") setPhase("scanned");
          schedulePoll(qrCode, (result.interval ?? 3) * 1000, 0);
        } catch {
          if (!aliveRef.current) return;
          // 连续失败上限：超限按过期处理，避免无限轮询
          if (failures + 1 >= MAX_POLL_FAILURES) {
            setPhase("expired");
            return;
          }
          schedulePoll(qrCode, intervalMs, failures + 1);
        }
      }, intervalMs);
    },
    [onToken],
  );

  const begin = useCallback(async () => {
    setPhase("loading");
    setErrorMessage(null);
    setQrDataUrl(null);
    if (pollTimer.current) clearTimeout(pollTimer.current);
    try {
      const session = await channelApi.startWeixinRegistration();
      if (!aliveRef.current) return;
      setPhase("pending");
      await renderQr(session.qr_url);
      schedulePoll(session.qr_code, (session.interval ?? 3) * 1000);
    } catch (e) {
      if (!aliveRef.current) return;
      setPhase("error");
      setErrorMessage(e instanceof Error ? e.message : String(e));
    }
  }, [renderQr, schedulePoll]);

  const busy = phase === "loading";
  const showQr = phase === "pending" || phase === "scanned";
  return (
    <div className="es-field" data-testid="weixin-qr-login">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={begin}
          disabled={busy}
          loading={busy}
          leftIcon={<QrCode size={16} />}
        >
          {t("channel.weixin.scanLogin")}
        </Button>
        {phase === "scanned" && (
          <span className="text-12 text-theme-text-muted">
            {t("channel.weixin.qrScanned")}
          </span>
        )}
        {(phase === "expired" || phase === "error") && (
          <span
            className="text-12 text-red-500 dark:text-red-400"
            role="alert"
          >
            {phase === "expired"
              ? t("channel.weixin.qrExpired")
              : errorMessage || t("channel.weixin.qrFailed")}
          </span>
        )}
      </div>
      {(showQr || busy) && (
        <div className="mt-3 flex flex-col items-center">
          <div className="flex w-[224px] max-w-full aspect-square items-center justify-center rounded-xl border border-[var(--theme-border)] bg-white p-3 shadow-sm">
            {qrDataUrl ? (
              <ImageWithSkeleton
                src={qrDataUrl}
                alt={t("channel.weixin.scanLogin")}
                skipUrlResolve
                inline
                className="size-full"
              />
            ) : (
              <LoadingSpinner size="md" />
            )}
          </div>
          {showQr && (
            <div
              role="status"
              className="mt-3 text-14 font-medium text-[var(--theme-primary)]"
            >
              {t("channel.weixin.qrWaiting")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
