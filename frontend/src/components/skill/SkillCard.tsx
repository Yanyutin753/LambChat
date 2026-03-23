import {
  FileText,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  Package,
  ShoppingBag,
  User,
  Globe,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillResponse } from "../../types";

interface SkillCardProps {
  skill: SkillResponse;
  onToggle: (name: string) => void;
  onEdit: (skill: SkillResponse) => void;
  onDelete: (name: string) => void;
  onPublish?: (name: string) => void;
  isPublished?: boolean;
  marketplaceIsActive?: boolean;
}

const SOURCE_COLORS: Record<string, string> = {
  builtin:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
  marketplace:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  manual: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
};

const DEFAULT_SOURCE_COLOR =
  "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300";

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  builtin: <Package size={10} />,
  marketplace: <ShoppingBag size={10} />,
  manual: <User size={10} />,
};

export function SkillCard({
  skill,
  onToggle,
  onEdit,
  onDelete,
  onPublish,
  isPublished,
  marketplaceIsActive,
}: SkillCardProps) {
  const { t } = useTranslation();
  const sourceLabel = t(`skillSelector.sources.${skill.source}`, skill.source);
  const sourceColor = SOURCE_COLORS[skill.source] || DEFAULT_SOURCE_COLOR;

  return (
    <div
      className={`panel-card transition-opacity ${
        !skill.enabled ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <FileText
              size={20}
              className="text-stone-400 dark:text-stone-500 flex-shrink-0"
            />
            <h4 className="font-medium text-stone-900 dark:text-stone-100 truncate">
              {skill.name}
            </h4>
            <span
              className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${sourceColor}`}
            >
              {SOURCE_ICONS[skill.source]}
              {sourceLabel}
            </span>
            {isPublished && (
              <span className="flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/50 dark:text-green-300">
                <Globe size={10} />
                {t("skills.card.published")}
              </span>
            )}
            {!skill.enabled && (
              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-500">
                {t("skills.card.disabled")}
              </span>
            )}
          </div>

          {/* Description */}
          <p className="mt-2 text-sm text-stone-600 dark:text-stone-400 line-clamp-2">
            {skill.description || t("skills.noDescription")}
          </p>

          {/* Timestamps */}
          {skill.updated_at && (
            <div className="mt-2 text-xs text-stone-400 dark:text-stone-500">
              {t("skills.card.updated")}:{" "}
              {new Date(skill.updated_at).toLocaleDateString()}
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
          <button
            onClick={() => onToggle(skill.name)}
            className="btn-icon"
            title={
              skill.enabled ? t("skills.card.disable") : t("skills.card.enable")
            }
          >
            {skill.enabled ? (
              <ToggleRight
                size={20}
                className="text-green-600 dark:text-green-500"
              />
            ) : (
              <ToggleLeft size={20} />
            )}
          </button>
          <button
            onClick={() => onEdit(skill)}
            className="btn-icon"
            title={t("skills.card.edit")}
          >
            <Edit3 size={20} />
          </button>
          {skill.source === "manual" && onPublish && (
            <button
              onClick={() => onPublish(skill.name)}
              className="btn-icon"
              title={
                isPublished
                  ? t("skills.card.republish")
                  : t("skills.card.publishToMarketplace")
              }
            >
              {isPublished ? (
                marketplaceIsActive === false ? (
                  <Globe
                    size={20}
                    className="text-amber-500 dark:text-amber-400"
                  />
                ) : (
                  <Globe
                    size={20}
                    className="text-green-600 dark:text-green-500"
                  />
                )
              ) : (
                <Globe size={20} className="text-stone-400 dark:text-stone-500" />
              )}
            </button>
          )}
          <button
            onClick={() => onDelete(skill.name)}
            className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
            title={t("skills.card.delete")}
          >
            <Trash2 size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}
