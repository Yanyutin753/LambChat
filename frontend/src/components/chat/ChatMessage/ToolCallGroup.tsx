import { useId, type ReactNode } from "react";
import { ChevronRight, FileText, Search, Terminal, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import { InteractiveIcon } from "../../common/InteractiveIcon";
import { useUiExpansionState } from "./uiExpansionStore";
import type { ToolGroupCategory } from "./runStepsCollapseUtils";

const icons = {
  read: FileText,
  search: Search,
  execute: Terminal,
  other: Wrench,
};
const labels = {
  read: "toolGroupRead",
  search: "toolGroupSearch",
  execute: "toolGroupExecute",
  other: "toolGroupOther",
};

export function ToolCallGroup({
  count,
  category,
  stateKey,
  renderExpanded,
}: {
  count: number;
  category: ToolGroupCategory;
  stateKey: string;
  renderExpanded: () => ReactNode;
}) {
  const { t } = useTranslation();
  const contentId = useId();
  const [expanded, , setExpanded] = useUiExpansionState(stateKey, false);
  const Icon = icons[category];
  return (
    <div className="chat-tool-category">
      <div className="chat-tool-call-group" data-category={category}>
        <div className="chat-tool-call-group__header">
          <button
            type="button"
            className="chat-tool-call-group__toggle"
            aria-expanded={expanded}
            aria-controls={expanded ? contentId : undefined}
            onClick={() => setExpanded(!expanded)}
          >
            <span className="chat-tool-call-group__icon">
              <InteractiveIcon>
                <Icon size={16} />
              </InteractiveIcon>
            </span>
            <span className="min-w-0 flex-1 truncate text-left">
              {t(`chat.message.${labels[category]}`, { count })}
            </span>
            <span className="chat-tool-call-group__chevron" aria-hidden="true">
              <ChevronRight
                size={12}
                className={`shrink-0 text-theme-text-tertiary transition-transform motion-reduce:transition-none ${
                  expanded ? "rotate-90" : ""
                }`}
              />
            </span>
          </button>
        </div>
        {expanded && (
          <div id={contentId} className="chat-tool-call-group__panel">
            <div className="chat-tool-call-group__content">
              <div className="chat-tool-call-group__rows">
                {renderExpanded()}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
