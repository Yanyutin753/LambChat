import { MessageSquare } from "lucide-react";
import type { ReactNode } from "react";
import { SceneIllustration, type IllustrationScene } from "./SceneIllustration";

export interface EmptyStateProps {
  /** Avatar-derived artwork matching the panel's purpose. */
  illustration?: IllustrationScene;
  icon?: ReactNode;
  /** Primary text (already translated) */
  title: ReactNode;
  /** Secondary/hint text (already translated) */
  description?: ReactNode;
  /** Optional action slot (button, link, etc.) */
  action?: ReactNode;
  /** Extra CSS classes on root */
  className?: string;
}

/**
 * Shared empty-state placeholder used across panels.
 * Uses the `skill-empty-state` BEM classes defined in skill.css.
 *
 * Replaces 5+ inline duplications of the same HTML structure
 * in MarketplacePanel, SkillsList, ModelConfigTab, TeamRoster,
 * PersonaPlazaPanel, etc.
 */
export function EmptyState({
  illustration,
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={`skill-empty-state ${className ?? ""}`}>
      {illustration ? (
        <SceneIllustration scene={illustration} />
      ) : (
        <div
          aria-hidden="true"
          className="flex size-10 shrink-0 items-center justify-center rounded-full bg-theme-bg-subtle text-theme-text-tertiary [&>svg]:size-5"
        >
          {icon ?? <MessageSquare size={20} />}
        </div>
      )}
      <p className="skill-empty-state__title">{title}</p>
      {description && (
        <p className="skill-empty-state__description">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
