import { useEffect } from "react";
import { isMobileDevice, scrollFocusedInputIntoView } from "../utils/mobile";
import {
  getAppViewportState,
  shouldPreferVisibleViewportHeight,
  shouldUpdateAppViewportHeight,
} from "../components/layout/AppContent/appViewport";

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

export function isStandaloneDisplayMode(): boolean {
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

export function useAppViewport() {
  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const rootStyle = document.documentElement.style;
    let raf = 0;
    let viewportHeightValue: string | null = "";
    let viewportOffsetTopValue: string | null = "";
    let keyboardInsetValue: string | null = "";
    let keyboardOpenValue: string | null = "";
    let unfocusedHeight = window.innerHeight;
    let viewportWidth = window.innerWidth;

    const updateViewportHeight = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const visualViewportHeight = window.visualViewport?.height ?? null;
        const visualViewportOffsetTop = window.visualViewport?.offsetTop ?? 0;
        const windowInnerHeight = window.innerHeight;
        const keyboardFocused = isEditableElementFocused();
        if (window.innerWidth !== viewportWidth) {
          viewportWidth = window.innerWidth;
          unfocusedHeight = windowInnerHeight;
        } else if (!keyboardFocused && keyboardOpenValue !== "true") {
          unfocusedHeight = windowInnerHeight;
        }
        const viewportState = getAppViewportState({
          visualViewportHeight,
          visualViewportOffsetTop,
          windowInnerHeight,
          editableFocused: keyboardFocused,
          layoutViewportResized:
            Number.parseFloat(
              rootStyle.getPropertyValue("--app-native-keyboard-height"),
            ) > 0 ||
            (isMobileDevice() && unfocusedHeight - windowInnerHeight > 100),
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

    const handleVisibleViewportChange = () => {
      updateViewportHeight();
      scrollFocusedInputIntoView();
    };
    updateViewportHeight();
    window.visualViewport?.addEventListener(
      "resize",
      handleVisibleViewportChange,
    );
    window.visualViewport?.addEventListener("scroll", updateViewportHeight);
    window.addEventListener("resize", handleVisibleViewportChange);
    window.addEventListener("orientationchange", updateViewportHeight);
    document.addEventListener("focusin", updateViewportHeight);
    document.addEventListener("focusout", updateViewportHeight);

    return () => {
      cancelAnimationFrame(raf);
      window.visualViewport?.removeEventListener(
        "resize",
        handleVisibleViewportChange,
      );
      window.visualViewport?.removeEventListener(
        "scroll",
        updateViewportHeight,
      );
      window.removeEventListener("resize", handleVisibleViewportChange);
      window.removeEventListener("orientationchange", updateViewportHeight);
      document.removeEventListener("focusin", updateViewportHeight);
      document.removeEventListener("focusout", updateViewportHeight);
      rootStyle.removeProperty("--app-viewport-height");
      rootStyle.removeProperty("--app-viewport-offset-top");
      rootStyle.removeProperty("--app-keyboard-inset");
      document.documentElement.removeAttribute("data-mobile-keyboard");
    };
  }, []);
}
