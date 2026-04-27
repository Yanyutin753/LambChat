import { useState, useRef, useEffect, memo } from "react";
import { createPortal } from "react-dom";
import { Brain, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AgentOption } from "../../types";
import { ICON_MAP, THINKING_LEVEL_COLOR } from "./chatInputConstants";

interface AgentOptionButtonProps {
  optionKey: string;
  option: AgentOption;
  value: boolean | string | number;
  onChange: (value: boolean | string | number) => void;
}

export const AgentOptionButton = memo(function AgentOptionButton({
  optionKey: _optionKey,
  option,
  value,
  onChange,
}: AgentOptionButtonProps) {
  const { t } = useTranslation();
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const portalRef = useRef<HTMLDivElement>(null);
  const mobileSheetRef = useRef<HTMLDivElement>(null);

  const label = option.label_key ? t(option.label_key) : option.label;
  const description = option.description_key
    ? t(option.description_key)
    : option.description || label;

  const IconComponent = option.icon ? ICON_MAP[option.icon] : null;

  useEffect(() => {
    if (!showDropdown) return;

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
  }, [showDropdown]);

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

    const getDropdownStyle = (): React.CSSProperties => {
      const rect = dropdownRef.current?.getBoundingClientRect();
      if (!rect) return { display: "none" };
      const vw = window.innerWidth;
      const dropdownW = Math.min(288, vw - 16);
      const left = Math.max(8, Math.min(rect.left, vw - dropdownW - 8));
      return {
        position: "fixed",
        bottom: window.innerHeight - rect.top + 4,
        left,
        width: dropdownW,
        zIndex: 9999,
      };
    };

    const ActiveIcon = IconComponent || Brain;
    const isOff = String(value) === "off";
    const levelColor =
      THINKING_LEVEL_COLOR[String(value)] ?? THINKING_LEVEL_COLOR.off;

    return (
      <div ref={dropdownRef}>
        <button
          type="button"
          onClick={() => setShowDropdown(!showDropdown)}
          className="chat-tool-btn"
          style={
            isOff
              ? undefined
              : {
                  borderColor: levelColor.border,
                  background: levelColor.bg,
                  color: levelColor.text,
                }
          }
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
                className="sm:hidden fixed inset-0 z-[9999] flex flex-col justify-end"
                onClick={() => setShowDropdown(false)}
              >
                <div className="absolute inset-0 bg-black/40" />
                <div
                  className="relative rounded-t-2xl px-4 pt-3 pb-6 animate-in fade-in slide-in-from-bottom-4 duration-200"
                  style={{
                    background: "var(--theme-bg-card)",
                    maxHeight: "60vh",
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
                  <div className="flex flex-col gap-1">
                    {options.map((opt) => {
                      const isActive = opt.value === value;
                      const optColor =
                        THINKING_LEVEL_COLOR[String(opt.value)] ??
                        THINKING_LEVEL_COLOR.off;
                      return (
                        <button
                          key={String(opt.value)}
                          type="button"
                          onClick={() => {
                            onChange(opt.value);
                            setShowDropdown(false);
                          }}
                          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors text-left active:scale-[0.98]"
                          style={{
                            background: isActive
                              ? `color-mix(in srgb, ${optColor.text} 12%, transparent)`
                              : "transparent",
                            color: isActive
                              ? optColor.text
                              : "var(--theme-text)",
                          }}
                        >
                          <span
                            className="w-2.5 h-2.5 rounded-full shrink-0"
                            style={{
                              background: isActive
                                ? optColor.text
                                : "var(--theme-border)",
                            }}
                          />
                          {opt.label_key
                            ? t(opt.label_key)
                            : opt.label || String(opt.value)}
                          {isActive && (
                            <span
                              className="ml-auto text-xs"
                              style={{ color: optColor.text }}
                            >
                              ✓
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Desktop: dropdown with stepped slider */}
              <div
                ref={portalRef}
                className="hidden sm:block w-72 rounded-xl px-2 py-1.5 border shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-200"
                style={{
                  ...getDropdownStyle(),
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

                <div className="mx-2 mb-1">
                  <div className="stepped-slider select-none">
                    <div
                      className="relative h-10 flex items-center cursor-pointer"
                      role="slider"
                      tabIndex={0}
                      aria-valuemin={0}
                      aria-valuemax={options.length - 1}
                      aria-valuenow={options.findIndex(
                        (opt) => opt.value === value,
                      )}
                      onClick={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const clientX = (e.nativeEvent as MouseEvent).clientX;
                        const ratio = Math.max(
                          0,
                          Math.min(1, (clientX - rect.left) / rect.width),
                        );
                        const idx = Math.round(ratio * (options.length - 1));
                        const opt = options[idx];
                        if (opt) onChange(opt.value);
                      }}
                      onKeyDown={(e) => {
                        const currentIdx = options.findIndex(
                          (opt) => opt.value === value,
                        );
                        if (
                          e.key === "ArrowRight" &&
                          currentIdx < options.length - 1
                        ) {
                          onChange(options[currentIdx + 1].value);
                        } else if (e.key === "ArrowLeft" && currentIdx > 0) {
                          onChange(options[currentIdx - 1].value);
                        }
                      }}
                    >
                      <div
                        className="absolute left-0 right-0 h-1 rounded-full"
                        style={{
                          background: "var(--theme-border)",
                        }}
                      />
                      <div
                        className="absolute left-0 h-1 rounded-full transition-all duration-150"
                        style={{
                          width: `${
                            (options.findIndex((opt) => opt.value === value) /
                              (options.length - 1)) *
                            100
                          }%`,
                          background:
                            levelColor.text ?? "var(--theme-text-secondary)",
                        }}
                      />
                      {options.map((opt, idx) => {
                        const pos = (idx / (options.length - 1)) * 100;
                        const isActive = opt.value === value;
                        return (
                          <div
                            key={String(opt.value)}
                            className="absolute w-1.5 h-1.5 rounded-full -translate-x-1/2 transition-colors duration-150"
                            style={{
                              left: `${pos}%`,
                              background: isActive
                                ? levelColor.text ??
                                  "var(--theme-text-secondary)"
                                : "var(--theme-text-secondary)",
                              opacity: isActive ? 1 : 0.5,
                            }}
                          />
                        );
                      })}
                      <div
                        className="absolute w-4 h-4 rounded-full -translate-x-1/2 transition-all duration-150 shadow-sm hover:scale-105"
                        style={{
                          left: `${
                            (options.findIndex((opt) => opt.value === value) /
                              (options.length - 1)) *
                            100
                          }%`,
                          background:
                            levelColor.text ?? "var(--theme-text-secondary)",
                          border: "2px solid var(--theme-bg-card)",
                        }}
                      />
                    </div>
                    <div className="relative h-4 -mt-1">
                      {options.map((opt, idx) => {
                        const pos = (idx / (options.length - 1)) * 100;
                        const isActive = opt.value === value;
                        return (
                          <button
                            key={String(opt.value)}
                            type="button"
                            onClick={() => onChange(opt.value)}
                            className="absolute text-[10px] leading-tight text-center transition-all duration-150 cursor-pointer -translate-x-1/2 whitespace-nowrap"
                            style={{
                              left: `${pos}%`,
                              color: isActive
                                ? levelColor.text ??
                                  "var(--theme-text-secondary)"
                                : "var(--theme-text-secondary)",
                              fontWeight: isActive ? 500 : 400,
                            }}
                          >
                            {opt.label_key
                              ? t(opt.label_key)
                              : opt.label || String(opt.value)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
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
