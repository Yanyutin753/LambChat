import { lazy, Suspense, type ReactNode } from "react";
import { useAutoUpdate } from "../../hooks/useAutoUpdate";
import type { DesktopOs } from "../layout/TitleBar/titlebarPlatform";

const UpdateDialog = lazy(() =>
  import("./UpdateDialog").then((module) => ({ default: module.UpdateDialog })),
);
const DesktopTitlebarFrame = lazy(() =>
  import("../layout/TitleBar/DesktopTitlebarFrame").then((module) => ({
    default: module.DesktopTitlebarFrame,
  })),
);

export default function NativeUpdateShell({
  platform,
  titlebarOs,
  children,
}: {
  platform: "tauri" | "android" | "ios";
  titlebarOs: DesktopOs | null;
  children?: ReactNode;
}) {
  const { state, showDialog, setShowDialog, startUpdate, skipThisVersion } = useAutoUpdate();

  if (titlebarOs) {
    return (
      <Suspense fallback={
        <div className="flex h-full min-h-0 flex-col">
          <div className="h-10 shrink-0" />
          <div className="min-h-0 flex-1">{children}</div>
        </div>
      }>
        <DesktopTitlebarFrame
          os={titlebarOs}
          updateState={state}
          onInstallUpdate={startUpdate}
          onSkipVersion={skipThisVersion}
        >
          {children}
        </DesktopTitlebarFrame>
      </Suspense>
    );
  }

  return (
    <>
      {(platform === "android" || platform === "ios") && showDialog && state.available && (
        <Suspense fallback={null}>
          <UpdateDialog
            state={state}
            isOpen={showDialog}
            onUpgrade={startUpdate}
            onSkipVersion={skipThisVersion}
            onDismiss={() => setShowDialog(false)}
            platform={platform}
          />
        </Suspense>
      )}
      {children}
    </>
  );
}
