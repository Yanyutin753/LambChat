import { useEffect, type ReactNode } from "react";
import { ProfileModal } from "../../profile/ProfileModal";
import { Header } from "./Header";
import {
  getAppViewportState,
  isKeyboardViewport,
  shouldPreferVisibleViewportHeight,
  shouldUpdateAppViewportHeight,
} from "./appViewport";
import {
  getBrowserChromeNudgeScrollY,
  shouldNudgeBrowserChrome,
} from "./appBrowserChrome";
import { isMobileDevice } from "../../../utils/mobile";
import type { Project, VersionInfo } from "../../../types";
import type { TabType } from "./types";
import type { PluginRuntimeContributionStates } from "../../../extensions/coreContributions";

function isEditableElementFocused(): boolean {
  if (typeof document === "undefined") return false;
  const activeElement = document.activeElement;
  if (!activeElement) return false;
  if (
    activeElement instanceof HTMLInputElement ||
    activeElement instanceof HTMLTextAreaElement ||
    activeElement instanceof HTMLSelectElement
  ) {
    return true;
  }
  return (
    activeElement instanceof HTMLElement && activeElement.isContentEditable
  );
}

function isStandaloneDisplayMode(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return false;
  }

  const navigatorWithStandalone = navigator as Navigator & {
    standalone?: boolean;
  };

  return (
    navigatorWithStandalone.standalone === true ||
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.matchMedia?.("(display-mode: fullscreen)").matches
  );
}

export interface AppShellProps {
  activeTab: TabType;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: VersionInfo | null;
  setMobileSidebarOpen: (open: boolean) => void;
  currentProjectId: string | null;
  projectManager: { projects: Project[] };
  onNewSession: () => void;
  onShowProfile: () => void;
  sidebar?: ReactNode;
  children: ReactNode;
  // Model selection
  availableModels?:
    | {
        id: string;
        value: string;
        provider?: string;
        label: string;
        description?: string;
      }[]
    | null;
  currentModelId?: string;
  onSelectModel?: (modelId: string, modelValue: string) => void;
  // Share
  sessionId?: string | null;
  // Outline
  showOutlineButton?: boolean;
  onToggleOutline?: () => void;
  runtimePlugins?: PluginRuntimeContributionStates;
}

export function AppShell({
  activeTab,
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
  setMobileSidebarOpen,
  currentProjectId,
  projectManager,
  onNewSession,
  onShowProfile,
  sidebar,
  children,
  availableModels,
  currentModelId,
  onSelectModel,
  sessionId,
  showOutlineButton,
  onToggleOutline,
  runtimePlugins,
}: AppShellProps) {
  const appSafeAreaTop =
    "var(--app-safe-area-top-active, max(var(--app-safe-area-top, 0px), var(--app-fullscreen-safe-area-top, 0px)))";
  const appSafeAreaBottom =
    "var(--app-safe-area-bottom-active, max(var(--app-safe-area-bottom, 0px), var(--app-fullscreen-safe-area-bottom, 0px)))";

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const enabled = shouldNudgeBrowserChrome({
      isMobileDevice: isMobileDevice(),
      isStandaloneDisplayMode: isStandaloneDisplayMode(),
      hasVisualViewport: Boolean(window.visualViewport),
    });

    if (!enabled) return undefined;

    document.documentElement.setAttribute("data-browser-chrome-nudge", "true");

    let raf = 0;
    const nudgeBrowserChrome = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const top = getBrowserChromeNudgeScrollY({
          scrollHeight: document.documentElement.scrollHeight,
          innerHeight: window.innerHeight,
        });
        if (top > 0 && window.scrollY < top) {
          window.scrollTo(0, top);
        }
      });
    };

    const timers = [120, 420, 900].map((delay) =>
      window.setTimeout(nudgeBrowserChrome, delay),
    );
    nudgeBrowserChrome();
    window.addEventListener("resize", nudgeBrowserChrome);
    window.addEventListener("orientationchange", nudgeBrowserChrome);

    return () => {
      cancelAnimationFrame(raf);
      timers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener("resize", nudgeBrowserChrome);
      window.removeEventListener("orientationchange", nudgeBrowserChrome);
      document.documentElement.removeAttribute("data-browser-chrome-nudge");
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const rootStyle = document.documentElement.style;
    let raf = 0;
    let viewportHeightValue: string | null = "";
    let viewportOffsetTopValue: string | null = "";
    let keyboardInsetValue: string | null = "";
    let keyboardOpenValue: string | null = "";

    const updateViewportHeight = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const visualViewportHeight = window.visualViewport?.height ?? null;
        const visualViewportOffsetTop = window.visualViewport?.offsetTop ?? 0;
        const windowInnerHeight = window.innerHeight;
        const keyboardViewport = isKeyboardViewport({
          visualViewportHeight,
          windowInnerHeight,
        });
        const keyboardFocused = keyboardViewport && isEditableElementFocused();
        const viewportState = getAppViewportState({
          visualViewportHeight,
          visualViewportOffsetTop,
          windowInnerHeight,
          editableFocused: keyboardFocused,
          preferVisibleViewportHeight: shouldPreferVisibleViewportHeight({
            isMobileDevice: isMobileDevice(),
            isStandaloneDisplayMode: isStandaloneDisplayMode(),
            hasVisualViewport: Boolean(window.visualViewport),
          }),
        });
        const nextViewportHeightValue = viewportState.heightCssValue;
        const nextViewportOffsetTopValue = viewportState.offsetTopCssValue;
        const nextKeyboardInsetValue = viewportState.keyboardInsetCssValue;
        const nextKeyboardOpenValue = viewportState.keyboardOpen
          ? "true"
          : null;

        if (
          shouldUpdateAppViewportHeight(
            viewportHeightValue,
            nextViewportHeightValue,
          )
        ) {
          viewportHeightValue = nextViewportHeightValue;
          if (nextViewportHeightValue == null) {
            rootStyle.removeProperty("--app-viewport-height");
          } else {
            rootStyle.setProperty(
              "--app-viewport-height",
              nextViewportHeightValue,
            );
          }
        }

        if (
          shouldUpdateAppViewportHeight(
            viewportOffsetTopValue,
            nextViewportOffsetTopValue,
          )
        ) {
          viewportOffsetTopValue = nextViewportOffsetTopValue;
          if (nextViewportOffsetTopValue == null) {
            rootStyle.removeProperty("--app-viewport-offset-top");
          } else {
            rootStyle.setProperty(
              "--app-viewport-offset-top",
              nextViewportOffsetTopValue,
            );
          }
        }

        if (
          shouldUpdateAppViewportHeight(
            keyboardInsetValue,
            nextKeyboardInsetValue,
          )
        ) {
          keyboardInsetValue = nextKeyboardInsetValue;
          if (nextKeyboardInsetValue == null) {
            rootStyle.removeProperty("--app-keyboard-inset");
          } else {
            rootStyle.setProperty(
              "--app-keyboard-inset",
              nextKeyboardInsetValue,
            );
          }
        }

        if (keyboardOpenValue !== nextKeyboardOpenValue) {
          keyboardOpenValue = nextKeyboardOpenValue;
          if (nextKeyboardOpenValue == null) {
            document.documentElement.removeAttribute("data-mobile-keyboard");
          } else {
            document.documentElement.setAttribute(
              "data-mobile-keyboard",
              nextKeyboardOpenValue,
            );
          }
        }
      });
    };

    updateViewportHeight();
    window.visualViewport?.addEventListener("resize", updateViewportHeight);
    window.visualViewport?.addEventListener("scroll", updateViewportHeight);
    window.addEventListener("resize", updateViewportHeight);
    window.addEventListener("orientationchange", updateViewportHeight);
    document.addEventListener("focusin", updateViewportHeight);
    document.addEventListener("focusout", updateViewportHeight);

    return () => {
      cancelAnimationFrame(raf);
      window.visualViewport?.removeEventListener(
        "resize",
        updateViewportHeight,
      );
      window.visualViewport?.removeEventListener(
        "scroll",
        updateViewportHeight,
      );
      window.removeEventListener("resize", updateViewportHeight);
      window.removeEventListener("orientationchange", updateViewportHeight);
      document.removeEventListener("focusin", updateViewportHeight);
      document.removeEventListener("focusout", updateViewportHeight);
      rootStyle.removeProperty("--app-viewport-height");
      rootStyle.removeProperty("--app-viewport-offset-top");
      rootStyle.removeProperty("--app-keyboard-inset");
      document.documentElement.removeAttribute("data-mobile-keyboard");
    };
  }, []);

  return (
    <>
      <ProfileModal
        showProfileModal={showProfileModal}
        onCloseProfileModal={onCloseProfileModal}
        versionInfo={versionInfo}
      />

      <div
        className="flex w-full overflow-hidden"
        style={{
          backgroundColor: "var(--theme-bg)",
          boxSizing: "content-box",
          paddingTop: appSafeAreaTop,
          paddingBottom: appSafeAreaBottom,
          height: `calc(var(--app-viewport-height, 100dvh) - ${appSafeAreaTop} - ${appSafeAreaBottom})`,
          transform: "translate3d(0, var(--app-viewport-offset-top, 0px), 0)",
        }}
      >
        {sidebar}

        <div className="relative z-0 flex flex-1 min-w-0 flex-col overflow-hidden">
          <Header
            activeTab={activeTab}
            setMobileSidebarOpen={setMobileSidebarOpen}
            currentProjectId={currentProjectId}
            projectManager={projectManager}
            onNewSession={onNewSession}
            onShowProfile={onShowProfile}
            availableModels={availableModels}
            currentModelId={currentModelId}
            onSelectModel={onSelectModel}
            sessionId={sessionId}
            showOutlineButton={showOutlineButton}
            onToggleOutline={onToggleOutline}
            runtimePlugins={runtimePlugins}
          />

          {children}
        </div>
      </div>
    </>
  );
}
