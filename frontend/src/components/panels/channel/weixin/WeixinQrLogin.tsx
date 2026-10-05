import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { QrCode, RefreshCw } from "lucide-react";
import { Button } from "../../../common";
import { channelApi } from "../../../../services/api/channel";

type QrPhase = "idle" | "loading" | "pending" | "scanned" | "expired" | "error";

/** 轮询连续失败上限（约 3s×N），超限按过期处理 */
const MAX_POLL_FAILURES = 10;

/** 微信 iLink 扫码登录：展示二维码并轮询状态，成功后回填 bot_token */
export function WeixinQrLogin({
  onToken,
}: {
  onToken: (token: string) => void;
}) {
  const { t } = useTranslation();
  const [phase, setPhase] = useState<QrPhase>("idle");
  const [qrUrl, setQrUrl] = useState<string | null>(null);
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

  const schedulePoll = useCallback(
    (qrCode: string, intervalMs: number, failures = 0) => {
      pollTimer.current = setTimeout(async () => {
        if (!aliveRef.current) return;
        try {
          const result = await channelApi.pollWeixinRegistration(qrCode);
          if (!aliveRef.current) return;
          if (result.status === "success" && result.bot_token) {
            setPhase("idle");
            setQrUrl(null);
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
    if (pollTimer.current) clearTimeout(pollTimer.current);
    try {
      const session = await channelApi.startWeixinRegistration();
      if (!aliveRef.current) return;
      setQrUrl(session.qr_url);
      setPhase("pending");
      schedulePoll(session.qr_code, (session.interval ?? 3) * 1000);
    } catch (e) {
      if (!aliveRef.current) return;
      setPhase("error");
      setErrorMessage(e instanceof Error ? e.message : String(e));
    }
  }, [schedulePoll]);

  const busy = phase === "loading";
  return (
    <div className="es-field" data-testid="weixin-qr-login">
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={begin} disabled={busy}>
          {busy ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : (
            <QrCode size={14} />
          )}
          {t("channel.weixin.scanLogin")}
        </Button>
        {(phase === "pending" || phase === "scanned") && (
          <span className="text-12 text-theme-text-muted">
            {phase === "scanned"
              ? t("channel.weixin.qrScanned")
              : t("channel.weixin.qrWaiting")}
          </span>
        )}
        {(phase === "expired" || phase === "error") && (
          <span className="text-12 text-theme-text-danger" role="alert">
            {phase === "expired"
              ? t("channel.weixin.qrExpired")
              : errorMessage || t("channel.weixin.qrFailed")}
          </span>
        )}
      </div>
      {qrUrl && (phase === "pending" || phase === "scanned") && (
        <div className="mt-2 flex justify-center rounded-lg border border-[var(--theme-border-subtle)] bg-white p-3">
          <img src={qrUrl} alt="WeChat QR" className="size-44 object-contain" />
        </div>
      )}
    </div>
  );
}
