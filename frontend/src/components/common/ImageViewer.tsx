import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  X,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  RotateCw,
  Maximize2,
} from "lucide-react";

interface ImageViewerProps {
  src: string; // Image URL
  alt?: string; // Image description
  isOpen: boolean; // Show/hide
  onClose: () => void; // Close callback
}

// Scale range and step
const MIN_SCALE = 0.1;
const MAX_SCALE = 5;
const SCALE_STEP = 0.25;

export function ImageViewer({
  src,
  alt = "",
  isOpen,
  onClose,
}: ImageViewerProps) {
  const { t } = useTranslation();
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Reset state when opening
  useEffect(() => {
    if (isOpen) {
      setScale(1);
      setRotation(0);
      setPosition({ x: 0, y: 0 });
    }
  }, [isOpen]);

  // Handle ESC key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Lock body scroll when open
  useEffect(() => {
    if (!isOpen) return;

    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  // Handle mouse wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -SCALE_STEP : SCALE_STEP;
    setScale((prev) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev + delta)));
  }, []);

  // Handle drag start
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return; // Only left click
      e.preventDefault();
      setIsDragging(true);
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
    },
    [position],
  );

  // Handle drag move
  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      setPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, dragStart]);

  // Zoom controls
  const zoomIn = useCallback(() => {
    setScale((prev) => Math.min(MAX_SCALE, prev + SCALE_STEP));
  }, []);

  const zoomOut = useCallback(() => {
    setScale((prev) => Math.max(MIN_SCALE, prev - SCALE_STEP));
  }, []);

  // Rotate controls
  const rotateLeft = useCallback(() => {
    setRotation((prev) => prev - 90);
  }, []);

  const rotateRight = useCallback(() => {
    setRotation((prev) => prev + 90);
  }, []);

  // Reset to original state
  const reset = useCallback(() => {
    setScale(1);
    setRotation(0);
    setPosition({ x: 0, y: 0 });
  }, []);

  // Handle background click to close
  const handleBackgroundClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose],
  );

  // Don't render if not open
  if (!isOpen) return null;

  const scalePercentage = Math.round(scale * 100);

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex flex-col bg-black/90"
      onClick={handleBackgroundClick}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/50 backdrop-blur-sm">
        {/* Close button */}
        <button
          type="button"
          onClick={onClose}
          className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer"
          aria-label={t("common.close")}
        >
          <X size={24} className="text-white" />
        </button>

        {/* Controls */}
        <div className="flex items-center gap-1">
          {/* Rotate left */}
          <button
            type="button"
            onClick={rotateLeft}
            className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer"
            aria-label={t("imageViewer.rotateLeft")}
          >
            <RotateCcw size={20} className="text-white" />
          </button>

          {/* Rotate right */}
          <button
            type="button"
            onClick={rotateRight}
            className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer"
            aria-label={t("imageViewer.rotateRight")}
          >
            <RotateCw size={20} className="text-white" />
          </button>

          {/* Divider */}
          <div className="w-px h-6 bg-white/20 mx-2" />

          {/* Zoom out */}
          <button
            type="button"
            onClick={zoomOut}
            disabled={scale <= MIN_SCALE}
            className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label={t("imageViewer.zoomOut")}
          >
            <ZoomOut size={20} className="text-white" />
          </button>

          {/* Scale percentage */}
          <span className="min-w-[60px] text-center text-white text-sm font-medium">
            {scalePercentage}%
          </span>

          {/* Zoom in */}
          <button
            type="button"
            onClick={zoomIn}
            disabled={scale >= MAX_SCALE}
            className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label={t("imageViewer.zoomIn")}
          >
            <ZoomIn size={20} className="text-white" />
          </button>

          {/* Divider */}
          <div className="w-px h-6 bg-white/20 mx-2" />

          {/* Reset */}
          <button
            type="button"
            onClick={reset}
            className="flex items-center justify-center w-10 h-10 rounded-lg hover:bg-white/10 transition-colors cursor-pointer"
            aria-label={t("imageViewer.reset")}
          >
            <Maximize2 size={20} className="text-white" />
          </button>
        </div>

        {/* Empty space for balance */}
        <div className="w-10" />
      </div>

      {/* Main area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden relative"
        onWheel={handleWheel}
      >
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{
            cursor: scale > 1 ? (isDragging ? "grabbing" : "grab") : "default",
          }}
        >
          <img
            src={src}
            alt={alt}
            className="max-w-full max-h-full object-contain select-none"
            style={{
              transform: `translate(${position.x}px, ${position.y}px) scale(${scale}) rotate(${rotation}deg)`,
              transition: isDragging ? "none" : "transform 0.1s ease-out",
            }}
            onMouseDown={handleMouseDown}
            draggable={false}
          />
        </div>
      </div>

      {/* Hint */}
      <div className="flex items-center justify-center px-4 py-2 bg-black/50 backdrop-blur-sm">
        <p className="text-white/60 text-xs">{t("imageViewer.hint")}</p>
      </div>
    </div>,
    document.body,
  );
}
