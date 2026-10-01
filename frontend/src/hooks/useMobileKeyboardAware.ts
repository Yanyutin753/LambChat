import { useState, useEffect } from "react";

/** Auth forms share the app's keyboard detection, including native WebView resize. */
export function useMobileKeyboardAware(): boolean {
  const [isKeyboardOpen, setIsKeyboardOpen] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    const update = () =>
      setIsKeyboardOpen(root.dataset.mobileKeyboard === "true");
    update();
    const observer = new MutationObserver(update);
    observer.observe(root, {
      attributes: true,
      attributeFilter: ["data-mobile-keyboard"],
    });
    return () => observer.disconnect();
  }, []);

  return isKeyboardOpen;
}
