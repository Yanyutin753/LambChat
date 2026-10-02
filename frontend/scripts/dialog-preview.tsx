/** UI-only dialog preview: no native updater, mail client, or write API is invoked. */
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import i18n from "../src/i18n";
import { applyThemeToDocument, isTheme } from "../src/utils/themeDom";
import { UpdateDialog } from "../src/components/update/UpdateDialog";
import { ContactAdminDialog } from "../src/components/common/ContactAdminDialog";
import { Button } from "../src/components/common/ui/Button";
import type { UpdateState } from "../src/types";
import "../src/fonts.css";
import "../src/styles/tailwind.css";
import "../src/styles/tokens.css";
import "../src/styles/base.css";
import "../src/styles/components.css";
import "../src/styles/animations.css";

void import("../src/fonts-cjk");
const params = new URLSearchParams(location.search);
const theme = params.get("theme");
applyThemeToDocument(isTheme(theme) ? theme : "light");
await i18n.changeLanguage(params.get("lang") || "zh");

export function DialogPreview() {
  const [open, setOpen] = useState(true);
  const attempts = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [state, setState] = useState<UpdateState>({
    available: true,
    version: params.has("long") ? `99.0.0-${"preview".repeat(12)}` : "99.0.0",
    releaseNotes: params.has("long")
      ? `## 更新说明\n\n${"更清楚地阅读任务状态，并继续您的工作。\n\n".repeat(8)}\n\n\`preview-${"long-path".repeat(20)}\`\n\n| Module | Change |\n| --- | --- |\n| Rendering | ${"responsive".repeat(20)} |`
      : "## 更新说明\n\n- 优化手机布局。\n- 改善查找与键盘操作。",
    releaseUrl: "https://example.test/release/99.0.0",
    releaseAssets: [],
    publishedAt: "2026-10-02T00:00:00Z",
    downloading: params.get("state") === "downloading",
    progress: 42,
    downloaded: 50 * 1024 * 1024,
    contentLength: 120 * 1024 * 1024,
    readyToInstall: params.get("state") === "ready",
    error:
      params.get("state") === "error" ? "Fixture update unavailable" : null,
    linuxInstallSource: params.get("source") === "unknown" ? "unknown" : null,
  });
  useEffect(() => () => clearTimeout(timer.current), []);
  const upgrade = () => {
    if (state.readyToInstall) return setOpen(false);
    setState((value) => ({ ...value, downloading: true, error: null }));
    timer.current = setTimeout(() => {
      attempts.current += 1;
      setState((value) => ({
        ...value,
        downloading: false,
        error: attempts.current === 1 ? "Fixture update unavailable" : null,
        readyToInstall: attempts.current > 1,
      }));
    }, 2000);
  };
  const close = () => setOpen(false);
  return (
    <main style={{ height: "100dvh", padding: 16 }}>
      <Button onClick={() => setOpen(true)}>Open dialog</Button>
      {params.get("view") === "contact" ? (
        <ContactAdminDialog
          isOpen={open}
          onClose={close}
          reason={
            params.get("reason") === "permission"
              ? "noPermission"
              : "emailActivation"
          }
        />
      ) : (
        <UpdateDialog
          state={state}
          isOpen={open}
          platform={
            params.get("platform") === "ios"
              ? "ios"
              : params.get("platform") === "tauri"
                ? "tauri"
                : "android"
          }
          onUpgrade={upgrade}
          onSkip={close}
          onSkipVersion={close}
          onDismiss={close}
        />
      )}
    </main>
  );
}
const root = createRoot(document.getElementById("root")!);
root.render(<DialogPreview />);
import.meta.hot?.dispose(() => root.unmount());
