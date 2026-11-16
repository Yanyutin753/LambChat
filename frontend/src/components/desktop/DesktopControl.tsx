import { useEffect, useId, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { LogicalSize } from "@tauri-apps/api/dpi";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useTranslation } from "react-i18next";
import { Monitor, Pause, Play, GripVertical } from "lucide-react";
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
      .setSize(new LogicalSize(460, expanded ? 96 : 56))
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
  if (overlay) {
    return (
      <div
        aria-hidden="true"
        className={`desktop-control-overlay${
          paused || unavailable || error ? " is-inactive" : ""
        }`}
      />
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
        <GripVertical
          className="desktop-control-grip"
          aria-hidden="true"
          size={16}
        />
        <span className="desktop-control-icon">
          <Monitor aria-hidden="true" size={18} />
        </span>
        <div className="desktop-control-copy">
          <p id={statusId} role="status">
            {t(`desktopControl.${state || "waiting"}`)}
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
