import {
  FileText,
  ToggleLeft,
  ToggleRight,
  Edit3,
  Trash2,
  Github,
  Package,
  User,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillResponse } from "../../types";

interface SkillCardProps {
  skill: SkillResponse;
  onToggle: (name: string) => void;
  onEdit: (skill: SkillResponse) => void;
  onDelete: (name: string, isSystem: boolean) => void;
}

const SOURCE_COLORS: Record<string, string> = {
  builtin: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  github:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  manual: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
};

const DEFAULT_SOURCE_COLOR =
  "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300";

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  builtin: <Package size={10} />,
  github: <Github size={10} />,
  manual: <User size={10} />,
};

export function SkillCard({
  skill,
  onToggle,
  onEdit,
  onDelete,
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
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                skill.is_system
                  ? "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300"
                  : "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300"
              }`}
            >
              {skill.is_system
                ? t("skills.card.system")
                : t("skills.card.user")}
            </span>
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

          {/* GitHub URL */}
          {skill.github_url && (
            <div className="mt-1 text-xs text-stone-500 dark:text-stone-500 truncate">
              <Github size={12} className="inline mr-1" />
              {skill.github_url}
            </div>
          )}

          {/* Version */}
          {skill.version && (
            <div className="mt-1 text-xs text-stone-400 dark:text-stone-500">
              v{skill.version}
            </div>
          )}

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
          {skill.can_edit && (
            <>
              <button
                onClick={() => onEdit(skill)}
                className="btn-icon"
                title={t("skills.card.edit")}
              >
                <Edit3 size={20} />
              </button>
              <button
                onClick={() => onDelete(skill.name, skill.is_system)}
                className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                title={t("skills.card.delete")}
              >
                <Trash2 size={20} />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
