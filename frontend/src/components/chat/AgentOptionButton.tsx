import { useState, useRef, useEffect, memo, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Brain, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import type { AgentOption } from "../../types";
import { ICON_MAP } from "./chatInputConstants";

interface AgentOptionButtonProps {
  optionKey: string;
  option: AgentOption;
  value: boolean | string | number;
  onChange: (value: boolean | string | number) => void;
  /** 面板内提示行（如沙箱本地档离线说明），渲染在描述下方。 */
  note?: string;
  /** 面板底部操作区（如沙箱离线时的下载引导），渲染在档位列表下方。 */
  footer?: ReactNode;
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

function AgentOptionRow({
  option,
  isActive,
  onSelect,
}: {
  option: NonNullable<AgentOption["options"]>[number];
  isActive: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors text-left cursor-pointer active:scale-[0.98]${
        option.disabled ? " opacity-50" : ""
      }`}
      style={{
        background: isActive
          ? "color-mix(in srgb, var(--theme-primary) 12%, transparent)"
          : "transparent",
        color: isActive ? "var(--theme-primary)" : "var(--theme-text)",
      }}
    >
      <span
        className="w-2.5 h-2.5 rounded-full shrink-0"
        style={{
          background: isActive ? "var(--theme-primary)" : "var(--theme-border)",
        }}
      />
      {option.label_key
        ? t(option.label_key)
        : option.label || String(option.value)}
      {isActive && (
        <span
          className="ml-auto text-xs"
          style={{ color: "var(--theme-primary)" }}
        >
          ✓
        </span>
      )}
    </button>
  );
}

export const AgentOptionButton = memo(function AgentOptionButton({
  optionKey: _optionKey,
  option,
  value,
  onChange,
  note,
  footer,
  isOpen: externalIsOpen,
  onOpenChange: externalOnOpenChange,
}: AgentOptionButtonProps) {
  const { t } = useTranslation();
  const [internalShow, setInternalShow] = useState(false);
  const showDropdown = externalOnOpenChange
    ? externalIsOpen ?? false
    : internalShow;
  const setShowDropdown = externalOnOpenChange ?? setInternalShow;
  const dropdownRef = useRef<HTMLDivElement>(null);
  const portalRef = useRef<HTMLDivElement>(null);
  const mobileSheetRef = useRef<HTMLDivElement>(null);

  const label = option.label_key ? t(option.label_key) : option.label;
  const description = option.description_key
    ? t(option.description_key)
    : option.description || label;

  const IconComponent = option.icon ? ICON_MAP[option.icon] : null;

  useEffect(() => {
    if (!showDropdown || externalOnOpenChange) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        dropdownRef.current?.contains(target) ||
        portalRef.current?.contains(target) ||
        mobileSheetRef.current?.contains(target)
      ) {
        return;
      }
      setShowDropdown(false);
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showDropdown, externalOnOpenChange, setShowDropdown]);

  // Compute dropdown style before any conditional returns — hooks must not be called conditionally
  const dropdownStyle = useStickyDropdownPosition(
    dropdownRef,
    showDropdown,
    (rect) => {
      const vw = window.innerWidth;
      const dropdownW = Math.min(288, vw - 16);
      const left = Math.max(8, Math.min(rect.left, vw - dropdownW - 8));
      return {
        position: "fixed" as const,
        bottom: window.innerHeight - rect.top + 4,
        left,
        width: dropdownW,
        zIndex: 9999,
      };
    },
  );

  if (externalOnOpenChange) {
    if (option.type === "boolean") return null;
    const options = option.options;
    if (options && options.length > 0) {
      return showDropdown
        ? createPortal(
            <>
              <div
                className="fixed inset-0 z-[300] bg-black/50 animate-fade-in"
                onClick={() => setShowDropdown(false)}
              />
              <div
                className="fixed z-[301] sm:inset-0 sm:flex sm:items-center sm:justify-center sm:p-4 inset-x-0 bottom-0 animate-slide-up sm:animate-scale-in"
                onClick={() => setShowDropdown(false)}
              >
                <div
                  className="sm:rounded-2xl rounded-t-2xl shadow-2xl px-4 pt-3 safe-area-bottom [--safe-area-bottom-extra:1.5rem] sm:[--safe-area-bottom-extra:1rem] animate-in fade-in slide-in-from-bottom-4 sm:scale-in-95 sm:slide-in-from-bottom-0 duration-200 sm:w-[28rem] sm:max-w-[90vw]"
                  style={{
                    background: "var(--theme-bg-card)",
                    maxHeight: "60dvh",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div
                    className="mx-auto mb-3 w-9 h-1 rounded-full sm:hidden"
                    style={{ background: "var(--theme-border)" }}
                  />
                  <div
                    className="text-sm font-medium mb-3"
                    style={{ color: "var(--theme-text)" }}
                  >
                    {description}
                  </div>
                  {note && (
                    <div
                      className="text-xs mb-3 px-2.5 py-1.5 rounded-lg"
                      style={{
                        color: "var(--theme-text-secondary)",
                        background:
                          "color-mix(in srgb, var(--theme-border) 30%, transparent)",
                      }}
                    >
                      {note}
                    </div>
                  )}
                  <div className="flex flex-col gap-1">
                    {options.map((opt) => (
                      <AgentOptionRow
                        key={String(opt.value)}
                        option={opt}
                        isActive={opt.value === value}
                        onSelect={() => {
                          onChange(opt.value);
                          setShowDropdown(false);
                        }}
                      />
                    ))}
                  </div>
                  {footer && (
                    <div
                      className="mt-2 pt-1 border-t"
                      style={{ borderColor: "var(--theme-border)" }}
                    >
                      {footer}
                    </div>
                  )}
                </div>
              </div>
            </>,
            document.body,
          )
        : null;
    }
    return null;
  }

  if (option.type === "boolean") {
    const isActive = value === true;
    return (
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`flex items-center justify-center rounded-full p-2 border transition-all duration-300 ${
          isActive ? "chat-tool-btn-active" : "chat-tool-btn"
        }`}
        title={description}
      >
        {IconComponent ? <IconComponent size={18} /> : <Settings size={18} />}
      </button>
    );
  }

  const options = option.options;
  if (options && options.length > 0) {
    const selectedOption = options.find((opt) => opt.value === value);
    const selectedLabel = selectedOption?.label_key
      ? t(selectedOption.label_key)
      : selectedOption?.label || String(value);

    const ActiveIcon = IconComponent || Brain;

    return (
      <div ref={dropdownRef}>
        <button
          type="button"
          onClick={() => setShowDropdown(!showDropdown)}
          className="chat-tool-btn"
          title={`${description}: ${selectedLabel}`}
        >
          <ActiveIcon size={18} />
        </button>

        {showDropdown &&
          createPortal(
            <>
              {/* Mobile: bottom sheet modal */}
              <div
                ref={mobileSheetRef}
                className="safe-area-viewport-padding-top sm:hidden fixed inset-0 z-[9999] flex flex-col justify-end"
                onClick={() => setShowDropdown(false)}
              >
                <div className="absolute inset-0 bg-black/40" />
                <div
                  className="relative rounded-t-2xl px-4 pt-3 safe-area-bottom [--safe-area-bottom-extra:1.5rem] animate-in fade-in slide-in-from-bottom-4 duration-200"
                  style={{
                    background: "var(--theme-bg-card)",
                    maxHeight: "60dvh",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div
                    className="mx-auto mb-3 w-9 h-1 rounded-full"
                    style={{ background: "var(--theme-border)" }}
                  />
                  <div
                    className="text-sm font-medium mb-3"
                    style={{ color: "var(--theme-text)" }}
                  >
                    {description}
                  </div>
                  {note && (
                    <div
                      className="text-xs mb-3 px-2.5 py-1.5 rounded-lg"
                      style={{
                        color: "var(--theme-text-secondary)",
                        background:
                          "color-mix(in srgb, var(--theme-border) 30%, transparent)",
                      }}
                    >
                      {note}
                    </div>
                  )}
                  <div className="flex flex-col gap-1">
                    {options.map((opt) => (
                      <AgentOptionRow
                        key={String(opt.value)}
                        option={opt}
                        isActive={opt.value === value}
                        onSelect={() => {
                          onChange(opt.value);
                          setShowDropdown(false);
                        }}
                      />
                    ))}
                  </div>
                  {footer && (
                    <div
                      className="mt-2 pt-1.5 border-t"
                      style={{ borderColor: "var(--theme-border)" }}
                    >
                      {footer}
                    </div>
                  )}
                </div>
              </div>

              {/* Desktop: plain dropdown list */}
              <div
                ref={portalRef}
                className="hidden sm:block w-72 rounded-xl px-2 py-1.5 border shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-200"
                style={{
                  ...dropdownStyle,
                  background: "var(--theme-bg-card)",
                  borderColor: "var(--theme-border)",
                }}
              >
                <div
                  className="px-2.5 py-1.5 text-xs font-medium"
                  style={{ color: "var(--theme-text-secondary)" }}
                >
                  {description}
                </div>
                {note && (
                  <div
                    className="px-2.5 pb-1.5 text-xs"
                    style={{ color: "var(--theme-text-secondary)" }}
                  >
                    {note}
                  </div>
                )}
                <div className="flex flex-col gap-1">
                  {options.map((opt) => (
                    <AgentOptionRow
                      key={String(opt.value)}
                      option={opt}
                      isActive={opt.value === value}
                      onSelect={() => {
                        onChange(opt.value);
                        setShowDropdown(false);
                      }}
                    />
                  ))}
                </div>
                {footer && (
                  <div
                    className="mt-2 pt-1.5 border-t"
                    style={{ borderColor: "var(--theme-border)" }}
                  >
                    {footer}
                  </div>
                )}
              </div>
            </>,
            document.body,
          )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() =>
        onChange(value === option.default ? !option.default : option.default)
      }
      className={`flex items-center justify-center rounded-full p-2 border transition-all duration-300 ${
        value !== option.default ? "chat-tool-btn-active" : "chat-tool-btn"
      }`}
      title={description}
    >
      {IconComponent ? <IconComponent size={18} /> : <Settings size={18} />}
    </button>
  );
});
