import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigationType, useNavigate } from "react-router-dom";
import {
  applyNavigation,
  canGoBack,
  canGoForward,
  createNavHistoryStack,
  resolvePopDelta,
  type NavHistoryStack,
} from "./navigationHistoryStack";

/**
 * 浏览器式前进/后退导航（桌面端标题栏）Provider：
 * 把 React Router 的 location / navigationType 事件翻译成
 * navigationHistoryStack 纯函数栈动作（PUSH/REPLACE/POP 位移），
 * 并暴露 canBack / canForward 与 Alt+←/→ 快捷键。
 */

function readBrowserHistoryIndex(): number | null {
  const state = window.history.state as { idx?: unknown } | null;
  return typeof state?.idx === "number" ? state.idx : null;
}

function locationKey(pathname: string, search: string): string {
  return pathname + search;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target.isContentEditable
  );
}

export interface NavigationHistoryValue {
  canBack: boolean;
  canForward: boolean;
  back: () => void;
  forward: () => void;
}

const NavigationHistoryContext = createContext<NavigationHistoryValue>({
  canBack: false,
  canForward: false,
  back: () => {},
  forward: () => {},
});

export function NavigationHistoryProvider({
  children,
}: {
  children: ReactNode;
}) {
  const location = useLocation();
  const navigationType = useNavigationType();
  const navigate = useNavigate();
  const [stack, setStack] = useState<NavHistoryStack>(() =>
    createNavHistoryStack(locationKey(location.pathname, location.search)),
  );
  const prevHistoryIdxRef = useRef<number | null>(readBrowserHistoryIndex());
  const stackRef = useRef(stack);
  stackRef.current = stack;

  useEffect(() => {
    const key = locationKey(location.pathname, location.search);
    setStack((prev) => {
      if (navigationType === "PUSH") {
        return applyNavigation(prev, { kind: "push", key });
      }
      if (navigationType === "REPLACE") {
        return applyNavigation(prev, { kind: "replace", key });
      }
      const nextIdx = readBrowserHistoryIndex();
      const delta = resolvePopDelta(prevHistoryIdxRef.current, nextIdx);
      return applyNavigation(
        prev,
        delta === null ? { kind: "replace", key } : { kind: "pop", delta, key },
      );
    });
    prevHistoryIdxRef.current = readBrowserHistoryIndex();
  }, [location, navigationType]);

  const value: NavigationHistoryValue = {
    canBack: canGoBack(stack),
    canForward: canGoForward(stack),
    back: () => {
      if (canGoBack(stackRef.current)) navigate(-1);
    },
    forward: () => {
      if (canGoForward(stackRef.current)) navigate(1);
    },
  };

  // Alt+←/→：桌面 WebView 与浏览器一致的导航快捷键。
  // 跳过可编辑目标（macOS Option+方向键是逐词移动光标）。
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || event.metaKey || event.ctrlKey || event.shiftKey) {
        return;
      }
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (isEditableTarget(event.target)) return;
      if (event.key === "ArrowLeft") {
        if (!canGoBack(stackRef.current)) return;
        event.preventDefault();
        navigate(-1);
      } else {
        if (!canGoForward(stackRef.current)) return;
        event.preventDefault();
        navigate(1);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);

  return (
    <NavigationHistoryContext.Provider value={value}>
      {children}
    </NavigationHistoryContext.Provider>
  );
}

export function useNavigationHistory(): NavigationHistoryValue {
  return useContext(NavigationHistoryContext);
}
