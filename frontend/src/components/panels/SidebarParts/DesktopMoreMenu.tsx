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
  userItems: MoreMenuItem[];
  sysItems: MoreMenuItem[];
  isOpen: boolean;
  onClose: () => void;
  menuRef: React.RefObject<HTMLDivElement | null>;
  position: { top: number; left: number };
}

export function DesktopMoreMenu({
  featureItems = [],
  userItems,
  sysItems,
  isOpen,
  onClose,
  menuRef,
  position,
}: DesktopMoreMenuProps) {
  const location = useLocation();
  const navigate = useNavigate();

  if (!isOpen) return null;

  const visibleFeature = featureItems.filter((i) => i.show);
  const visibleUser = userItems.filter((i) => i.show);
  const visibleSys = sysItems.filter((i) => i.show);

  const renderItem = (item: MoreMenuItem) => (
    <button
      key={item.path}
      type="button"
      className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)] active:scale-[0.98] ${
        (item.matchPaths ?? [item.path]).includes(location.pathname)
          ? "bg-[var(--theme-primary-light)] text-[var(--theme-text)]"
          : ""
      }`}
      onClick={() => {
        onClose();
        navigate(item.path);
      }}
    >
      <item.icon size={16} strokeWidth={1.8} />
      <span>{item.label}</span>
    </button>
  );

  const hasPrev = visibleFeature.length > 0 || visibleUser.length > 0;

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[301] w-52 rounded-xl shadow-xl border border-stone-200/60 dark:border-stone-800/60 overflow-hidden animate-scale-in bg-[var(--theme-bg-sidebar)]"
      style={{
        top: position.top,
        left: position.left,
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {visibleFeature.length > 0 && <div>{visibleFeature.map(renderItem)}</div>}
      {visibleUser.length > 0 && (
        <div>
          {visibleFeature.length > 0 && (
            <div className="mx-3 my-1 border-t border-[var(--theme-border)]" />
          )}
          {visibleUser.map(renderItem)}
        </div>
      )}
      {visibleSys.length > 0 && (
        <div>
          {hasPrev && (
            <div className="mx-3 my-1 border-t border-[var(--theme-border)]" />
          )}
          {visibleSys.map(renderItem)}
        </div>
      )}
    </div>,
    document.body,
  );
}
