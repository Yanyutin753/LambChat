import { ChevronsUpDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ImageWithSkeleton } from "../../chat/ChatMessage/ImageWithSkeleton";
import { getFullUrl } from "../../../services/api";

/** 侧边栏底部用户行：头像 + 用户名/角色 + 展开指示。 */
export function SidebarUserRow({
  user,
  imgError,
  onShowProfile,
}: {
  user: { username?: string; avatar_url?: string; roles?: string[] } | null;
  imgError: boolean;
  onShowProfile: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div
      onClick={onShowProfile}
      className="group flex items-center rounded-xl py-3 px-2 w-full hover:bg-stone-100 dark:hover:bg-stone-800/60 transition cursor-pointer"
    >
      <div className="shrink-0 w-8 h-8 rounded-full overflow-hidden ring-1 ring-stone-200 dark:ring-stone-700 group-hover:ring-[var(--theme-text-secondary)] transition mr-3">
        {user?.avatar_url && !imgError ? (
          <ImageWithSkeleton
            src={getFullUrl(user.avatar_url) ?? user.avatar_url}
            alt={user?.username || t("common.user")}
            skipUrlResolve
            inline
            className="w-full h-full object-cover rounded-full"
            style={{ borderRadius: "50%" }}
            errorFallback={
              <div className="flex w-full h-full items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full">
                <span className="text-xs font-semibold text-white font-serif">
                  {user?.username?.charAt(0).toUpperCase() || "U"}
                </span>
              </div>
            }
          />
        ) : (
          <div className="flex w-full h-full items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full">
            <span className="text-xs font-semibold text-white font-serif">
              {user?.username?.charAt(0).toUpperCase() || "U"}
            </span>
          </div>
        )}
      </div>
      <div className="flex-1 text-left min-w-0">
        <div className="text-sm font-medium font-serif text-stone-800 dark:text-stone-100 truncate">
          {user?.username || t("common.user")}
        </div>
        <div className="text-xs text-stone-400 dark:text-stone-500 whitespace-nowrap font-serif">
          {(user?.roles?.[0] || t("common.user")).replace(/^./, (c) =>
            c.toUpperCase(),
          )}
        </div>
      </div>
      <ChevronsUpDown className="size-4 text-stone-400 shrink-0" />
    </div>
  );
}
