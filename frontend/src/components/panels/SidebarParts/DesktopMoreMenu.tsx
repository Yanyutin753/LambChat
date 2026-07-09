import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { LucideIcon } from "lucide-react";

interface MoreMenuItem {
  path: string;
  label: string;
  icon: LucideIcon;
  show: boolean;
  matchPaths?: string[];
}

interface DesktopMoreMenuProps {
  featureItems?: MoreMenuItem[];
  isOpen: boolean;
  onClose: () => void;
  menuRef: React.RefObject<HTMLDivElement | null>;
  position: { top: number; left: number } | null;
}

export function DesktopMoreMenu({
  featureItems = [],
  isOpen,
  onClose,
  menuRef,
  position,
}: DesktopMoreMenuProps) {
  const location = useLocation();
  const navigate = useNavigate();

  if (!isOpen || !position) return null;

  const visibleItems = featureItems.filter((i) => i.show);

  const renderItem = (item: MoreMenuItem) => (
    <button
      key={item.path}
      type="button"
      className={`sidebar-nav-btn w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px] focus:outline-none transition-colors ${
        (item.matchPaths ?? [item.path]).includes(location.pathname)
          ? "bg-[var(--theme-bg-subtle)] text-[var(--theme-text)] font-medium"
          : ""
      }`}
      onClick={() => {
        onClose();
        navigate(item.path);
      }}
    >
      <item.icon size={20} />
      <span>{item.label}</span>
    </button>
  );

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[301] w-56 rounded-xl shadow-xl border overflow-hidden animate-scale-in"
      style={{
        top: position.top,
        left: position.left,
        backgroundColor: "var(--theme-bg-card)",
        borderColor: "var(--theme-border)",
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="flex flex-col gap-px p-2 space-y-1">
        {visibleItems.map(renderItem)}
      </div>
    </div>,
    document.body,
  );
}
