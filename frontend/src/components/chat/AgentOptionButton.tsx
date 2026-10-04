import { DialogCloseButton } from "../common/DialogCloseButton";
import { useState, memo, type ReactNode } from "react";
import { ModalSurface } from "../common/ModalSurface";
import { Brain, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";

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
  /** 档位列表下方、footer 上方的扩展区（如沙箱统一面板的执行设备列表）。 */
  belowOptions?: ReactNode;
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
      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-14 transition-colors text-left cursor-pointer active:scale-[0.98]${
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
          className="ml-auto text-12"
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
  belowOptions,
  isOpen: externalIsOpen,
  onOpenChange: externalOnOpenChange,
}: AgentOptionButtonProps) {
  const { t } = useTranslation();
  const [internalShow, setInternalShow] = useState(false);
  const showDropdown = externalOnOpenChange
    ? (externalIsOpen ?? false)
    : internalShow;
  const setShowDropdown = externalOnOpenChange ?? setInternalShow;
  const label = option.label_key ? t(option.label_key) : option.label;
  const description = option.description_key
    ? t(option.description_key)
    : option.description || label;

  const IconComponent = option.icon ? ICON_MAP[option.icon] : null;

  if (externalOnOpenChange && option.type === "boolean") return null;

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
      <>
        {!externalOnOpenChange && (
          <button
            type="button"
            onClick={() => setShowDropdown(!showDropdown)}
            className="chat-tool-btn"
            title={`${description}: ${selectedLabel}`}
          >
            <ActiveIcon size={18} />
          </button>
        )}
        <ModalSurface
          open={showDropdown}
          onClose={() => setShowDropdown(false)}
          label={description}
          className="modal-size-md"
        >
          <div
            className="w-full rounded-xl bg-theme-bg-card px-4 pt-3 pb-5"
            style={{
              maxHeight: "60dvh",
              overflowY: "auto",
              overscrollBehavior: "contain",
            }}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="min-w-0 text-14 font-medium font-serif text-theme-text">
                {description}
              </h3>
              <DialogCloseButton onClick={() => setShowDropdown(false)} />
            </div>
            {note && (
              <div className="text-12 mb-3 px-2.5 py-1.5 rounded-lg bg-theme-bg-subtle text-theme-text-secondary">
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
            {belowOptions}
            {footer && (
              <div className="mt-2 pt-1.5 border-t border-theme-border">
                {footer}
              </div>
            )}
          </div>
        </ModalSurface>
      </>
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
