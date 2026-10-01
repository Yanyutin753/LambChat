import { ModalSurface } from "../../common/ModalSurface";
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
}

export function MobileMoreMenuSheet({
  featureItems = [],
  isOpen,
  onClose,
  menuRef,
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
    <ModalSurface open onClose={onClose} label={t("nav.more")}>
      <div
        ref={menuRef}
        className="safe-area-x safe-area-bottom rounded-t-2xl shadow-xl max-h-[70dvh] overflow-y-auto"
        style={{ backgroundColor: "var(--theme-bg-card)" }}
      >
        <div className="flex items-center justify-between px-4 pb-1.5">
          <span className="text-13 font-medium text-[var(--theme-text)]">
            {t("nav.more", "更多")}
          </span>
          <button onClick={onClose} className="p-1 rounded-full ">
            <X size={16} className="text-[var(--theme-text-secondary)]" />
          </button>
        </div>
        <div className="flex flex-col gap-px px-2 pb-3 space-y-1">
          {visibleItems.map(renderItem)}
        </div>
      </div>
    </ModalSurface>
  );
}
