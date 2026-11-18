import { useEffect, useId, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { LogicalSize } from "@tauri-apps/api/dpi";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useTranslation } from "react-i18next";
import { Pause, Play } from "lucide-react";
import "./desktop-control.css";

export function DesktopControl({ overlay = false }: { overlay?: boolean }) {
  const { t } = useTranslation();
  const statusId = useId();
  const hintId = useId();
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
  const unavailable =
    state === "disconnected" || state === "unavailable" || state === "ended";
  const expanded = paused || unavailable || error || state === "stopping";
  useEffect(() => {
    if (overlay) return;
    void getCurrentWindow()
      .setSize(new LogicalSize(400, expanded ? 96 : 48))
      .catch(() => setError(true));
  }, [overlay, expanded]);
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
  const dots = (
    <span className="desktop-control-dots" aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  );
  const status = t(
    `desktopControl.${error ? "unavailable" : state || "waiting"}`,
  );
  if (overlay) {
    return (
      <div
        role="status"
        className={`desktop-control-overlay${
          paused || unavailable || error ? " is-inactive" : ""
        }`}
      >
        {dots}
        {status}
      </div>
    );
  }
  return (
    <main
      className="desktop-control"
      aria-label={t("desktopControl.title")}
      data-state={error ? "unavailable" : state}
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
        {dots}
        <div className="desktop-control-copy">
          <p id={statusId} role="status">
            {status}
          </p>
        </div>
      </header>
      <button
        type="button"
        aria-describedby={`${statusId} ${hintId}`}
        disabled={
          busy || state === "stopping" || unavailable || (paused && error)
        }
        onClick={() => void change(!paused)}
      >
        {paused ? (
          <Play aria-hidden="true" size={16} />
        ) : (
          <Pause aria-hidden="true" size={16} />
        )}
        {t(paused ? "desktopControl.resume" : "desktopControl.pause")}
      </button>
      <p
        id={hintId}
        className="desktop-control-hint"
        hidden={!expanded}
        role={error ? "alert" : undefined}
      >
        {t(
          error
            ? "desktopControl.error"
            : paused
              ? "desktopControl.resumeHint"
              : "desktopControl.hint",
        )}
      </p>
    </main>
  );
}
