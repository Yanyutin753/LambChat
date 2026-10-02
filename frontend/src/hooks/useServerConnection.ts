import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  normalizeServerUrl,
  setStoredServerUrl,
} from "../services/api/serverConfig";

/** Shared by first setup and settings; leaving either form invalidates its probe. */
export function useServerConnection() {
  const { t } = useTranslation();
  const request = useRef<AbortController | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");

  const cancel = useCallback(() => {
    request.current?.abort();
    request.current = null;
    setTesting(false);
    setError("");
  }, []);
  useEffect(
    () => () => {
      request.current?.abort();
      request.current = null;
    },
    [],
  );

  const connect = async (raw: string) => {
    const url = normalizeServerUrl(raw);
    if (!url || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setTesting(true);
    setError("");
    const timer = setTimeout(() => {
      if (request.current !== controller) return;
      cancel();
      setError(t("serverSetup.unreachable"));
    }, 15_000);
    controller.signal.addEventListener("abort", () => clearTimeout(timer), {
      once: true,
    });
    try {
      // Absolute health URL bypasses the old server's API rewrite.
      const response = await fetch(`${url}/health`, {
        method: "GET",
        signal: controller.signal,
      });
      if (request.current !== controller) return;
      if (!response.ok) {
        setError(t("serverSetup.fail", { status: String(response.status) }));
        return;
      }
      setStoredServerUrl(url);
      window.location.reload();
    } catch {
      if (request.current === controller)
        setError(t("serverSetup.unreachable"));
    } finally {
      clearTimeout(timer);
      if (request.current === controller) {
        request.current = null;
        setTesting(false);
      }
    }
  };
  return { testing, error, connect, cancel };
}
