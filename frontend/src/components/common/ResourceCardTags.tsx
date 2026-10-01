import { useCallback, useId, useRef, useState } from "react";
import { ResourceCardMenu } from "./ResourceCardMenu";
interface ResourceCardTagsProps {
  tags: string[];
  activeTag?: string | null;
  onToggle?: (tag: string) => void;
}

export function ResourceCardTags({
  tags,
  activeTag,
  onToggle,
}: ResourceCardTagsProps) {
  const menuId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const [position, setPosition] = useState<{ x: number; y: number } | null>(
    null,
  );
  const close = useCallback((restoreFocus = false) => {
    setPosition(null);
    if (restoreFocus) trigger.current?.focus();
  }, []);
  if (!tags.length) return null;
  return (
    <div className="flex min-w-0 flex-nowrap items-center gap-1.5">
      {tags.slice(0, 3).map((tag) => {
        const className = `scb__mini-tag min-w-0 ${activeTag === tag ? "scb__mini-tag--active" : ""}`;
        const label = <span className="truncate">{tag}</span>;
        return onToggle ? (
          <button
            key={tag}
            type="button"
            title={tag}
            className={className}
            aria-pressed={activeTag === tag}
            onClick={() => onToggle(tag)}
          >
            {label}
          </button>
        ) : (
          <span key={tag} title={tag} className={className}>
            {label}
          </span>
        );
      })}
      {tags.length > 3 &&
        (onToggle ? (
          <button
            ref={trigger}
            type="button"
            className="scb__mini-tag shrink-0"
            title={tags.slice(3).join(", ")}
            aria-haspopup="menu"
            aria-expanded={Boolean(position)}
            aria-controls={position ? menuId : undefined}
            onClick={(event) => {
              event.stopPropagation();
              if (position) {
                close(true);
                return;
              }
              const rect = event.currentTarget.getBoundingClientRect();
              setPosition({ x: rect.left, y: rect.bottom + 4 });
            }}
          >
            +{tags.length - 3}
          </button>
        ) : (
          <span
            className="scb__mini-tag shrink-0"
            title={tags.slice(3).join(", ")}
          >
            +{tags.length - 3}
          </span>
        ))}
      {position && onToggle && (
        <ResourceCardMenu
          id={menuId}
          title={tags.slice(3).join(", ")}
          position={position}
          onClose={close}
          actions={tags
            .slice(3)
            .map((tag) => ({ label: tag, onClick: () => onToggle(tag) }))}
        />
      )}
    </div>
  );
}
