import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { useStickyDropdownPosition } from "../../../hooks/useStickyDropdownPosition";

export interface SelectOption {
  value: string;
  label: ReactNode;
  group?: string;
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
  const requestedOpen = controlledOpen ?? localOpen;
  const open = requestedOpen && !disabled;
  const setOpen = useCallback(
    (next: boolean) => {
      setLocalOpen(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
  useEffect(() => {
    if (disabled && requestedOpen) setOpen(false);
  }, [disabled, requestedOpen, setOpen]);
  const ref = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const dropdownId = useId();
  const labelId = useId();

  const dropdownStyle = useStickyDropdownPosition(ref, open, (rect) => {
    const viewport = window.visualViewport;
    const viewportLeft = viewport?.offsetLeft ?? 0;
    const viewportTop = viewport?.offsetTop ?? 0;
    const viewportWidth = viewport?.width ?? window.innerWidth;
    const viewportBottom =
      viewportTop + (viewport?.height ?? window.innerHeight);
    const width = Math.min(
      Math.max(rect.width, 160),
      Math.max(0, viewportWidth - 32),
    );
    const left = Math.max(
      viewportLeft + 16,
      Math.min(rect.left, viewportLeft + viewportWidth - width - 16),
    );
    const anchorTop = Math.max(
      viewportTop + 16,
      Math.min(rect.top, viewportBottom - 16),
    );
    const anchorBottom = Math.max(
      viewportTop + 16,
      Math.min(rect.bottom, viewportBottom - 16),
    );
    const spaceBelow = viewportBottom - anchorBottom - 16;
    const spaceAbove = anchorTop - viewportTop - 16;
    const preferBelow = spaceBelow >= 200 || spaceBelow >= spaceAbove;
    return {
      position: "fixed",
      top: preferBelow ? anchorBottom + 4 : undefined,
      bottom: preferBelow ? undefined : window.innerHeight - anchorTop + 4,
      left,
      width,
      maxHeight: Math.max(
        0,
        Math.min(224, (preferBelow ? spaceBelow : spaceAbove) - 4),
      ),
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

  const optionGroups: { label?: string; options: SelectOption[] }[] = [];
  for (const option of options) {
    const previous = optionGroups[optionGroups.length - 1];
    if (previous && previous.label === option.group) {
      previous.options.push(option);
    } else {
      optionGroups.push({ label: option.group, options: [option] });
    }
  }

  const renderOption = (option: SelectOption) => (
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
        ref.current?.querySelector("button")?.focus();
        onChange(option.value);
      }}
    >
      {option.value === value && (
        <Check size={14} className="ui-select-option__check" />
      )}
      <span className="ui-select-option__label">{option.label}</span>
    </button>
  );

  return (
    <div ref={ref} className={cx("ui-select", className)}>
      <button
        type="button"
        disabled={disabled}
        className={cx("ui-select-trigger", triggerClassName)}
        aria-label={ariaLabel}
        aria-describedby={ariaLabel ? labelId : undefined}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? dropdownId : undefined}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
        onClick={() => !disabled && setOpen(!open)}
      >
        <span
          id={labelId}
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
            id={dropdownId}
            className={cx("ui-select-dropdown", dropdownClassName)}
            role="listbox"
            aria-label={ariaLabel}
            aria-labelledby={ariaLabel ? undefined : labelId}
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
            {optionGroups.map((group) =>
              group.label === undefined ? (
                group.options.map(renderOption)
              ) : (
                <div
                  key={group.options[0].value}
                  role="group"
                  aria-label={group.label}
                >
                  <div className="px-3 pb-1 pt-2 text-12 font-medium text-theme-text-secondary">
                    {group.label}
                  </div>
                  {group.options.map(renderOption)}
                </div>
              ),
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
