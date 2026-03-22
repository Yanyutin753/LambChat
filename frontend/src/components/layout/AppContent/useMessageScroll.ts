import { useRef, useEffect, useState, useCallback } from "react";
import type { VirtuosoHandle } from "react-virtuoso";

interface UseMessageScrollReturn {
  messagesContainerRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  virtuosoRef: React.RefObject<VirtuosoHandle | null>;
  virtuosoScrollerRef: React.RefObject<HTMLDivElement | null>;
  isNearBottom: boolean;
  showScrollTop: boolean;
  setShowScrollTop: React.Dispatch<React.SetStateAction<boolean>>;
  handleVirtuosoAtBottomChange: (atBottom: boolean) => void;
}

export function useMessageScroll(
  messages: { id: string }[],
): UseMessageScrollReturn {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const virtuosoScrollerRef = useRef<HTMLDivElement>(null);

  const [isNearBottom, setIsNearBottom] = useState(true);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const rafRef = useRef<number>(0);

  // Track previous message count to detect new messages
  const prevMessagesCountRef = useRef(messages.length);

  // Called by Virtuoso's atBottomStateChange
  const handleVirtuosoAtBottomChange = useCallback((atBottom: boolean) => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setIsNearBottom(atBottom);
      if (atBottom) setShowScrollTop(false);
    });
  }, []);

  // Attach scroll listener when Virtuoso Scroller mounts
  // Dependency on messages.length > 0 ensures re-run when Virtuoso first renders
  useEffect(() => {
    const scroller = virtuosoScrollerRef.current;
    if (!scroller) return;

    const lastScrollTop = { value: 0 };
    const lastScrollTime = { value: 0 };
    let timer: ReturnType<typeof setTimeout> | null = null;

    const handleScroll = () => {
      const now = Date.now();
      const scrollTop = scroller.scrollTop;
      const dt = now - lastScrollTime.value;
      const dScroll = lastScrollTop.value - scrollTop; // positive = scrolling up

      if (dt < 300 && dScroll > 30 && scrollTop > 200) {
        setShowScrollTop(true);
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => setShowScrollTop(false), 3000);
      } else if (scrollTop < 200) {
        setShowScrollTop(false);
      }

      lastScrollTop.value = scrollTop;
      lastScrollTime.value = now;
    };

    scroller.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scroller.removeEventListener("scroll", handleScroll);
      if (timer) clearTimeout(timer);
    };
  }, [messages.length > 0]);

  // Auto-scroll to bottom when new messages are added
  useEffect(() => {
    const prevCount = prevMessagesCountRef.current;
    const newCount = messages.length;

    if (newCount > prevCount) {
      virtuosoRef.current?.scrollTo({
        top: Number.MAX_SAFE_INTEGER,
        behavior: "auto",
      });
    }

    prevMessagesCountRef.current = newCount;
  }, [messages]);

  return {
    messagesContainerRef,
    messagesEndRef,
    virtuosoRef,
    virtuosoScrollerRef,
    isNearBottom,
    showScrollTop,
    setShowScrollTop,
    handleVirtuosoAtBottomChange,
  };
}
