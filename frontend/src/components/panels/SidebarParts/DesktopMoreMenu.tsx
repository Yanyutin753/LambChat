import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { LucideIcon } from "lucide-react";

interface MoreMenuItem {
  path: string;
  label: string;
  icon: LucideIcon;
  show: boolean;
}

interface DesktopMoreMenuProps {
  userItems: MoreMenuItem[];
  sysItems: MoreMenuItem[];
  isOpen: boolean;
  onClose: () => void;
  menuRef: React.RefObject<HTMLDivElement | null>;
  position: { top: number; left: number };
}

export function DesktopMoreMenu({
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

  const visibleUser = userItems.filter((i) => i.show);
  const visibleSys = sysItems.filter((i) => i.show);

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[301] w-52 rounded-xl shadow-xl border border-stone-200/60 dark:border-stone-800/60 overflow-hidden animate-scale-in bg-[var(--theme-bg-sidebar)]"
      style={{
        top: position.top,
        left: position.left,
      }}
    >
      {visibleUser.length > 0 && (
        <div>
          {visibleUser.map((item) => (
            <button
              key={item.path}
              type="button"
              className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)] active:scale-[0.98] ${
                location.pathname === item.path
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
          ))}
        </div>
      )}
      {visibleSys.length > 0 && (
        <div>
          {visibleUser.length > 0 && (
            <div className="mx-3 my-1 border-t border-[var(--theme-border)]" />
          )}
          {visibleSys.map((item) => (
            <button
              key={item.path}
              type="button"
              className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)] active:scale-[0.98] ${
                location.pathname === item.path
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
          ))}
        </div>
      )}
    </div>,
    document.body,
  );
}
