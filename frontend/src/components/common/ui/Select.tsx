import { useCallback, useEffect, useRef, useState } from "react";
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
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  ariaLabel?: string;
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
  open: controlledOpen,
  onOpenChange,
  ariaLabel,
  onChange,
  options,
  disabled = false,
  placeholder,
  className,
  triggerClassName,
  dropdownClassName,
}: SelectProps) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = useCallback(
    (next: boolean) => {
      setLocalOpen(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
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
  }, [open, setOpen]);

  useEffect(() => {
    if (open)
      (
        dropdownRef.current?.querySelector<HTMLButtonElement>(
          '[aria-selected="true"]:not(:disabled)',
        ) ??
        dropdownRef.current?.querySelector<HTMLButtonElement>(
          "button:not(:disabled)",
        )
      )?.focus();
  }, [open]);

  return (
    <div ref={ref} className={cx("ui-select", className)}>
      <button
        type="button"
        disabled={disabled}
        className={cx("ui-select-trigger", triggerClassName)}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
        onClick={() => !disabled && setOpen(!open)}
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
            aria-label={ariaLabel}
            onKeyDown={(event) => {
              if (event.key === "Escape" || event.key === "Tab") {
                event.stopPropagation();
                setOpen(false);
                ref.current?.querySelector("button")?.focus();
                if (event.key === "Escape") event.preventDefault();
              }
              if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key))
                return;
              event.preventDefault();
              const buttons = Array.from(
                event.currentTarget.querySelectorAll<HTMLButtonElement>(
                  "button:not(:disabled)",
                ),
              );
              const index = buttons.indexOf(
                document.activeElement as HTMLButtonElement,
              );
              const next =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? buttons.length - 1
                    : (index +
                        (event.key === "ArrowDown" ? 1 : -1) +
                        buttons.length) %
                      buttons.length;
              buttons[next]?.focus();
            }}
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
                  setOpen(false);
                  onChange(option.value);
                  ref.current?.querySelector("button")?.focus();
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
