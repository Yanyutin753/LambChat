import type { ReactNode } from "react";
import { Select } from "./ui";

export interface GlassSelectOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

interface GlassSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: GlassSelectOption[];
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

export function GlassSelect({
  value,
  onChange,
  options,
  disabled = false,
  placeholder,
  className,
}: GlassSelectProps) {
  return (
    <Select
      value={value}
      onChange={onChange}
      options={options}
      disabled={disabled}
      placeholder={placeholder ?? options[0]?.label ?? ""}
      className={className}
      triggerClassName="glass-input es-select-btn"
      dropdownClassName="glass-select-dropdown"
    />
  );
}
