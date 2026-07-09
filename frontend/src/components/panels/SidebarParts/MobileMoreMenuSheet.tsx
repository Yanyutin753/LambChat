import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { LucideIcon } from "lucide-react";

interface MoreMenuItem {
  path: string;
  label: string;
  icon: LucideIcon;
  show: boolean;
  matchPaths?: string[];
}

interface MobileMoreMenuSheetProps {
  featureItems?: MoreMenuItem[];
  isOpen: boolean;
  onClose: () => void;
  menuRef: React.RefObject<HTMLDivElement | null>;
  swipeRef: React.RefObject<HTMLElement | null>;
  dragHandleRef?: React.RefObject<HTMLDivElement | null>;
}

export function MobileMoreMenuSheet({
  featureItems = [],
  isOpen,
  onClose,
  menuRef,
  swipeRef,
  dragHandleRef,
}: MobileMoreMenuSheetProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (!isOpen) return null;

  const visibleItems = featureItems.filter((i) => i.show);

  const renderItem = (item: MoreMenuItem) => (
    <button
      key={item.path}
      type="button"
      className="sidebar-nav-btn w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px] focus:outline-none transition-colors"
      onClick={() => {
        onClose();
        navigate(item.path);
      }}
    >
      <item.icon size={20} />
      <span>{item.label}</span>
    </button>
  );

  return (
    <>
      <div
        className="safe-area-viewport-padding fixed inset-0 z-40 bg-black/50 sm:hidden"
        onClick={onClose}
      />
      <div
        ref={(el) => {
          (menuRef as React.RefObject<HTMLDivElement | null>).current = el;
          (swipeRef as React.RefObject<HTMLDivElement | null>).current = el;
        }}
        className="safe-area-viewport-padding fixed bottom-0 left-0 right-0 z-50 sm:hidden rounded-t-2xl shadow-xl max-h-[70dvh] overflow-y-auto"
        style={{ backgroundColor: "var(--theme-bg-card)" }}
      >
        <div className="flex justify-center py-2">
          <div
            ref={dragHandleRef}
            className="mobile-drag-handle w-10 h-1 rounded-full bg-[var(--theme-text-secondary)] opacity-25"
          />
        </div>
        <div className="flex items-center justify-between px-4 pb-1.5">
          <span className="text-[13px] font-medium text-[var(--theme-text)]">
            {t("nav.more", "更多")}
          </span>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-[var(--theme-bg-subtle)]"
          >
            <X size={16} className="text-[var(--theme-text-secondary)]" />
          </button>
        </div>
        <div className="flex flex-col gap-px px-2 pb-3 space-y-1">
          {visibleItems.map(renderItem)}
        </div>
      </div>
    </>
  );
}
