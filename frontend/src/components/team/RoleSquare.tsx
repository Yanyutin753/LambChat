import { useMemo } from "react";
import { Search, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PersonaPreset } from "../../types";
import { nameToGradient } from "../common/cardUtils";
import { PanelSearchInput } from "../common/PanelSearchInput";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../persona/PersonaAvatarIcon";
import {
  getEmojiAvatarUrl,
  isEmojiAvatar,
  isPersonaImageAvatar,
} from "../persona/personaAvatar";

interface RoleSquareProps {
  presets: PersonaPreset[];
  loading?: boolean;
  onAddRole: (preset: PersonaPreset) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

function renderAvatar(preset: PersonaPreset) {
  if (isPersonaImageAvatar(preset.avatar) || isEmojiAvatar(preset.avatar)) {
    return (
      <div
        className="scb__avatar-ring shrink-0"
        style={{ width: 28, height: 28 }}
      >
        <PersonaAvatarImage
          avatar={
            isEmojiAvatar(preset.avatar)
              ? getEmojiAvatarUrl(preset.avatar)
              : preset.avatar
          }
          alt=""
          className="scb__avatar-img"
        />
      </div>
    );
  }
  return (
    <div className="scb__icon-ring shrink-0" style={{ width: 28, height: 28 }}>
      <PersonaAvatarIcon
        avatar={preset.avatar}
        primaryTag={preset.tags[0]}
        size={16}
        className="text-[var(--theme-primary)]"
      />
    </div>
  );
}

export function RoleSquare({
  presets,
  loading,
  onAddRole,
  searchQuery,
  onSearchChange,
}: RoleSquareProps) {
  const { t } = useTranslation();
  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return presets;
    const q = searchQuery.toLowerCase();
    return presets.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        p.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [presets, searchQuery]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="team-pane-header">
        <div>
          <p className="team-pane-eyebrow">{t("team.select")}</p>
          <h2 className="team-pane-title font-serif">
            {t("team.roleLibrary")}
            <span className="team-pane-count">{filtered.length}</span>
          </h2>
        </div>
      </div>
      <div className="team-pane-tools">
        <div className="team-pane-search">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--theme-text-secondary)] pointer-events-none" />
          <PanelSearchInput
            type="text"
            placeholder={t("team.searchRoles")}
            value={searchQuery}
            onValueChange={onSearchChange}
            className="panel-search"
          />
        </div>
      </div>
      <div className="team-role-list">
        {loading && (
          <p className="py-8 text-center text-xs text-[var(--theme-text-secondary)]">
            {t("team.loadingRoles")}
          </p>
        )}
        {!loading && filtered.length === 0 && (
          <p className="py-8 text-center text-xs text-[var(--theme-text-secondary)]">
            {t("team.noRolesFound")}
          </p>
        )}
        {filtered.map((preset) => {
          const colors = nameToGradient(preset.name);
          return (
            <div
              key={preset.id}
              className="team-role-card group"
              style={{ "--team-accent": colors[0] } as React.CSSProperties}
            >
              {renderAvatar(preset)}
              <div className="team-role-card__body">
                <span className="team-role-card__name font-serif">
                  {preset.name}
                </span>
                {preset.description && (
                  <span className="team-role-card__desc">
                    {preset.description}
                  </span>
                )}
                {preset.tags.length > 0 && (
                  <div className="team-role-card__tags">
                    {preset.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="scb__mini-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => onAddRole(preset)}
                className="team-role-card__add"
                title={t("team.addToTeam")}
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
