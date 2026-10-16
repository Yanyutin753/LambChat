import type { ReactNode } from "react";
import {
  AccordionRoot,
  AccordionItem,
  AccordionHeader,
  AccordionTrigger,
  AccordionPanel,
} from "@lobehub/ui/es/base-ui/Accordion/atoms";
import {
  Check,
  ChevronRight,
  FileText,
  Search,
  Terminal,
  Wrench,
} from "lucide-react";
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
  const [expanded, , setExpanded] = useUiExpansionState(stateKey, false);
  const Icon = icons[category];
  return (
    <AccordionRoot
      value={expanded ? [stateKey] : []}
      onValueChange={(keys) => setExpanded(keys.includes(stateKey))}
      hideIndicator
      variant="borderless"
      className="chat-tool-category"
    >
      <AccordionItem
        value={stateKey}
        className="chat-tool-call-group"
        data-category={category}
      >
        <AccordionHeader className="chat-tool-call-group__header">
          <AccordionTrigger className="chat-tool-call-group__toggle">
            <span className="chat-tool-call-group__icon">
              <InteractiveIcon>
                <Icon size={16} />
              </InteractiveIcon>
            </span>
            <span className="min-w-0 flex-1 truncate text-left font-medium">
              {t(`chat.message.${labels[category]}`, { count })}
            </span>
            <span
              className="chat-tool-call-group__status"
              title={t("chat.todo.completed")}
            >
              <Check size={13} className="text-theme-success" />
              <span className="sr-only">{t("chat.todo.completed")}</span>
            </span>
            <ChevronRight
              size={14}
              className={`shrink-0 text-theme-text-tertiary transition-transform motion-reduce:transition-none ${
                expanded ? "rotate-90" : ""
              }`}
            />
          </AccordionTrigger>
        </AccordionHeader>
        <AccordionPanel
          keepMounted={false}
          className="chat-tool-call-group__panel"
          contentClassName="chat-tool-call-group__content"
        >
          {expanded && <div className="space-y-1">{renderExpanded()}</div>}
        </AccordionPanel>
      </AccordionItem>
    </AccordionRoot>
  );
}
