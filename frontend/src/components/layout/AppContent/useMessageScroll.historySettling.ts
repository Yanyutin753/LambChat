import { useCallback, useEffect, useRef, useState } from "react";

export interface MessageScrollHistorySettling {
  isHistoryScrollSettling: boolean;
  clearHistoryScrollSettling: () => void;
  startHistoryScrollSettling: () => void;
}

export function useMessageScrollHistorySettling(): MessageScrollHistorySettling {
  const [isHistoryScrollSettling, setIsHistoryScrollSettling] = useState(false);
  const historySettlingTimeoutRef = useRef<number>(0);

  const clearHistoryScrollSettling = useCallback(() => {
    if (historySettlingTimeoutRef.current) {
      window.clearTimeout(historySettlingTimeoutRef.current);
      historySettlingTimeoutRef.current = 0;
    }
    setIsHistoryScrollSettling(false);
  }, []);

  const startHistoryScrollSettling = useCallback(() => {
    setIsHistoryScrollSettling(true);
    if (historySettlingTimeoutRef.current) {
      window.clearTimeout(historySettlingTimeoutRef.current);
    }
    historySettlingTimeoutRef.current = window.setTimeout(() => {
      historySettlingTimeoutRef.current = 0;
      setIsHistoryScrollSettling(false);
    }, 2000);
  }, []);

  useEffect(() => clearHistoryScrollSettling, [clearHistoryScrollSettling]);

  return {
    isHistoryScrollSettling,
    clearHistoryScrollSettling,
    startHistoryScrollSettling,
  };
}
