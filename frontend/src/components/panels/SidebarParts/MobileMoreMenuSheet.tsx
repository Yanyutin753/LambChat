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
  userItems: MoreMenuItem[];
  sysItems: MoreMenuItem[];
  isOpen: boolean;
  onClose: () => void;
  menuRef: React.RefObject<HTMLDivElement | null>;
  swipeRef: React.RefObject<HTMLElement | null>;
}

export function MobileMoreMenuSheet({
  featureItems = [],
  userItems,
  sysItems,
  isOpen,
  onClose,
  menuRef,
  swipeRef,
}: MobileMoreMenuSheetProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  if (!isOpen) return null;

  const visibleFeature = featureItems.filter((i) => i.show);
  const visibleUser = userItems.filter((i) => i.show);
  const visibleSys = sysItems.filter((i) => i.show);

  const renderItem = (item: MoreMenuItem) => (
    <button
      key={item.path}
      type="button"
      className="w-full flex items-center gap-2.5 px-3 py-2.5 text-[13px] text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
      onClick={() => {
        onClose();
        navigate(item.path);
      }}
    >
      <item.icon size={16} />
      <span>{item.label}</span>
    </button>
  );

  const hasPrev = visibleFeature.length > 0 || visibleUser.length > 0;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50 sm:hidden"
        onClick={onClose}
      />
      <div
        ref={(el) => {
          (menuRef as React.RefObject<HTMLDivElement | null>).current = el;
          (swipeRef as React.RefObject<HTMLDivElement | null>).current = el;
        }}
        className="fixed bottom-0 left-0 right-0 z-50 sm:hidden bg-white dark:bg-stone-800 rounded-t-2xl shadow-xl max-h-[70vh] overflow-y-auto"
      >
        <div className="flex justify-center py-2">
          <div className="w-10 h-1 rounded-full bg-stone-300 dark:bg-stone-600" />
        </div>
        <div className="flex items-center justify-between px-4 pb-1.5">
          <span className="text-[13px] font-medium text-[var(--theme-text)]">
            {t("nav.more", "更多")}
          </span>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-stone-100 dark:hover:bg-stone-700"
          >
            <X size={16} className="text-stone-400" />
          </button>
        </div>
        <div className="px-2 pb-4">
          {visibleFeature.map(renderItem)}
          {visibleFeature.length > 0 && hasPrev && (
            <div className="h-px bg-stone-200 dark:bg-stone-700 my-1.5" />
          )}
          {visibleUser.map(renderItem)}
          {visibleUser.length > 0 && visibleSys.length > 0 && (
            <div className="h-px bg-stone-200 dark:bg-stone-700 my-1.5" />
          )}
          {visibleSys.map(renderItem)}
        </div>
      </div>
    </>
  );
}
