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
}: {
  typeValue: string;
  typeOnChange: (v: string) => void;
  sourceValue: string;
  sourceOnChange: (v: string) => void;
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
    </div>
  );
}
