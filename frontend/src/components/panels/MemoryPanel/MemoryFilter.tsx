import { useTranslation } from "react-i18next";
import { Filter } from "lucide-react";
import { PanelFilterSelect } from "../../common";
import {
  TYPE_OPTIONS,
  TYPE_DOTS,
  SOURCE_OPTIONS,
  SOURCE_DOTS,
} from "./constants";

export function MemoryFilter({
  typeValue,
  typeOnChange,
  sourceValue,
  sourceOnChange,
  contextValue,
  contextOnChange,
}: {
  typeValue: string;
  typeOnChange: (v: string) => void;
  sourceValue: string;
  sourceOnChange: (v: string) => void;
  contextValue: string;
  contextOnChange: (v: string) => void;
}) {
  const { t } = useTranslation();
  const typeOptions = TYPE_OPTIONS.map((opt) => {
    const dot = opt.value ? TYPE_DOTS[opt.value] : null;
    return {
      value: opt.value,
      label: (
        <>
          {dot ? (
            <span className={`h-2 w-2 rounded-full ${dot}`} />
          ) : (
            <Filter size={14} />
          )}
          <span className="panel-filter-trigger__label">{t(opt.labelKey)}</span>
        </>
      ),
    };
  });
  const sourceOptions = SOURCE_OPTIONS.map((opt) => {
    const dot = opt.value ? SOURCE_DOTS[opt.value] : null;
    return {
      value: opt.value,
      label: (
        <>
          {dot && <span className={`h-2 w-2 rounded-full ${dot}`} />}
          <span className="panel-filter-trigger__label">{t(opt.labelKey)}</span>
        </>
      ),
    };
  });

  return (
    <div className="flex shrink-0 items-center gap-2" data-filter-menu>
      <PanelFilterSelect
        value={typeValue}
        onChange={typeOnChange}
        options={typeOptions}
      />
      <PanelFilterSelect
        value={sourceValue}
        onChange={sourceOnChange}
        options={sourceOptions}
      />
      <input
        value={contextValue}
        onChange={(e) => contextOnChange(e.target.value)}
        placeholder={t("memory.contextFilterPlaceholder")}
        className="h-9 w-36 rounded-lg border border-border bg-input px-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        aria-label={t("memory.contextFilterPlaceholder")}
      />
    </div>
  );
}
