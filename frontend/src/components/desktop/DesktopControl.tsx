import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useTranslation } from "react-i18next";
import { Monitor, Pause, Play, GripHorizontal } from "lucide-react";
import "./desktop-control.css";

export function DesktopControl() {
  const { t } = useTranslation();
  const [state, setState] = useState("waiting");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const value = await invoke<string>("desktop_control_status", {
          ready: true,
        });
        if (!disposed) {
          setState(value);
          setError(false);
        }
      } catch {
        if (!disposed) setError(true);
      }
      if (!disposed) timer = setTimeout(() => void poll(), 250);
    };
    // A permit is only sent after the bundled control UI has painted.
    const frame = requestAnimationFrame(() => {
      void poll();
    });
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, []);
  const paused = state === "paused";
  const unavailable = state === "disconnected" || state === "unavailable";
  const change = async (pause: boolean) => {
    setBusy(true);
    try {
      await invoke("desktop_control_set_paused", { paused: pause });
      setState(pause ? "stopping" : "waiting");
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <main
      className="desktop-control"
      onKeyDown={(event) => {
        if (event.key === "Escape" && !paused && !busy) {
          event.preventDefault();
          void change(true);
        }
      }}
    >
      <header
        onPointerDown={(event) => {
          if (event.button === 0)
            void getCurrentWindow()
              .startDragging()
              .catch(() => setError(true));
        }}
      >
        <Monitor aria-hidden="true" size={16} />
        <strong>{t("desktopControl.title")}</strong>
        <GripHorizontal aria-hidden="true" size={16} />
      </header>
      <p role="status">{t(`desktopControl.${state || "waiting"}`)}</p>
      <p className="desktop-control-hint">
        {t(paused ? "desktopControl.resumeHint" : "desktopControl.hint")}
      </p>
      {error && <p role="alert">{t("desktopControl.error")}</p>}
      <button
        type="button"
        disabled={busy || state === "stopping" || unavailable}
        onClick={() => void change(!paused)}
      >
        {paused ? (
          <Play aria-hidden="true" size={16} />
        ) : (
          <Pause aria-hidden="true" size={16} />
        )}
        {t(paused ? "desktopControl.resume" : "desktopControl.pause")}
      </button>
    </main>
  );
}
