import { useState, useEffect, useRef, useCallback } from "react";
import { X } from "lucide-react";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

export interface EditorSidebarProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /** "default" (400px) | "wide" (500px) */
  width?: "default" | "wide";
}

export function EditorSidebar({
  open,
  onClose,
  title,
  subtitle,
  icon,
  children,
  footer,
  width = "default",
}: EditorSidebarProps) {
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 639px)").matches,
  );
  const [animateIn, setAnimateIn] = useState(false);
  const dragHandleRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Double-RAF animation to prevent flash
  useEffect(() => {
    if (!open) return;
    setAnimateIn(false);
    let cancelled = false;
    requestAnimationFrame(() => {
      if (cancelled) return;
      requestAnimationFrame(() => {
        if (cancelled) return;
        setAnimateIn(true);
      });
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Mobile body scroll lock
  useEffect(() => {
    if (open && isMobile) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open, isMobile]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.fullscreenElement) {
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Swipe to close on mobile
  const swipeRef = useSwipeToClose({
    onClose,
    enabled: open && isMobile,
    dragHandleRef,
    scrollContainerRef: bodyRef,
  });

  const setRef = useCallback(
    (el: HTMLDivElement | null) => {
      if (isMobile && swipeRef) {
        (swipeRef as React.RefObject<HTMLDivElement | null>).current = el;
      }
      if (!isMobile && dragHandleRef.current) {
        dragHandleRef.current = el;
      }
    },
    [isMobile, swipeRef],
  );

  if (!open) return null;

  return (
    <>
      {/* Overlay */}
      <div
        className={`editor-sidebar-overlay ${
          animateIn ? "editor-sidebar-overlay--visible" : ""
        }`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        ref={setRef}
        className={`editor-sidebar ${
          isMobile ? "editor-sidebar--mobile" : "editor-sidebar--sidebar"
        } ${width === "wide" ? "editor-sidebar--wide" : ""} ${
          animateIn ? "editor-sidebar--animate-in" : ""
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Mobile drag handle */}
        {isMobile && (
          <div ref={dragHandleRef} className="editor-sidebar-drag-handle" />
        )}

        {/* Header */}
        <div className="editor-sidebar-header">
          <div className="editor-sidebar-header-left">
            {icon && <div className="editor-sidebar-header-icon">{icon}</div>}
            <div className="min-w-0">
              <div className="editor-sidebar-header-title">{title}</div>
              {subtitle && (
                <div className="editor-sidebar-header-subtitle hidden sm:block">
                  {subtitle}
                </div>
              )}
            </div>
          </div>
          <button onClick={onClose} className="editor-sidebar-close-btn">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div ref={bodyRef} className="editor-sidebar-body">
          {children}
        </div>

        {/* Footer (outside scroll area) */}
        {footer && <div className="editor-sidebar-footer">{footer}</div>}
      </div>
    </>
  );
}
