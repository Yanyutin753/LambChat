import { useTranslation } from "react-i18next";
import { Select } from "../common/ui/Select";

export function SelectRow<T extends string>({
  label,
  value,
  options,
  open,
  onToggle,
  onSelect,
  loading,
  renderLabel,
}: {
  label: string;
  value: T;
  options: readonly { key: T; labelKey: string }[];
  open?: boolean;
  onToggle?: () => void;
  onSelect: (key: T) => void;
  loading?: boolean;
  renderLabel?: (key: T) => string;
}) {
  const { t } = useTranslation();
  return (
    <div className="profile-setting-row">
      <span className="text-14 text-theme-text">{label}</span>
      <Select
        open={open}
        onOpenChange={(next) => {
          if (next !== open) onToggle?.();
        }}
        value={value}
        onChange={(key) => onSelect(key as T)}
        disabled={loading}
        ariaLabel={label}
        options={options.map((option) => ({
          value: option.key,
          label: renderLabel ? renderLabel(option.key) : t(option.labelKey),
        }))}
      />
    </div>
  );
}
