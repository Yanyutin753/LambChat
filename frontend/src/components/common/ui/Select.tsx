import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { useStickyDropdownPosition } from "../../../hooks/useStickyDropdownPosition";

export interface SelectOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

export interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  disabled?: boolean;
  placeholder?: ReactNode;
  className?: string;
  triggerClassName?: string;
  dropdownClassName?: string;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function Select({
  value,
  onChange,
  options,
  disabled = false,
  placeholder,
  className,
  triggerClassName,
  dropdownClassName,
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const dropdownStyle = useStickyDropdownPosition(ref, open, (rect) => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const width = Math.max(rect.width, 160);
    const left = Math.max(16, Math.min(rect.left, viewportWidth - width - 16));
    const spaceBelow = viewportHeight - rect.bottom - 16;
    const spaceAbove = rect.top - 16;
    const preferBelow = spaceBelow >= 200 || spaceBelow >= spaceAbove;
    return {
      position: "fixed",
      top: preferBelow ? rect.bottom + 4 : undefined,
      bottom: preferBelow ? undefined : viewportHeight - rect.top + 4,
      left,
      width,
      zIndex: 9999,
    };
  });

  const selected = options.find((option) => option.value === value);
  const displayText = selected ? selected.label : placeholder;

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        ref.current &&
        !ref.current.contains(target) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className={cx("ui-select", className)}>
      <button
        type="button"
        disabled={disabled}
        className={cx("ui-select-trigger", triggerClassName)}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => !disabled && setOpen((current) => !current)}
      >
        <span
          className={
            selected
              ? "ui-select-trigger__label"
              : "ui-select-trigger__placeholder"
          }
        >
          {displayText ?? ""}
        </span>
        <ChevronDown
          size={15}
          className="ui-select-trigger__icon"
          style={{ transform: open ? "rotate(180deg)" : undefined }}
        />
      </button>

      {open &&
        createPortal(
          <div
            ref={dropdownRef}
            className={cx("ui-select-dropdown", dropdownClassName)}
            role="listbox"
            style={dropdownStyle}
          >
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={option.disabled}
                role="option"
                aria-selected={option.value === value}
                className={cx(
                  "ui-select-option",
                  option.value === value && "ui-select-option--active",
                  option.disabled && "ui-select-option--disabled",
                )}
                onClick={() => {
                  if (option.disabled) return;
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                {option.value === value && (
                  <Check size={14} className="ui-select-option__check" />
                )}
                <span className="ui-select-option__label">{option.label}</span>
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
