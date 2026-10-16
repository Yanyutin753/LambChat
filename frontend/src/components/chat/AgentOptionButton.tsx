import { InteractiveIcon } from "../common/InteractiveIcon";
import { DialogCloseButton } from "../common/DialogCloseButton";
import { useState, memo, type ReactNode } from "react";
import { ModalSurface } from "../common/ModalSurface";
import { Brain, Check, Cloud, Laptop, Settings } from "lucide-react";
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
  sandbox = false,
}: {
  option: NonNullable<AgentOption["options"]>[number];
  isActive: boolean;
  onSelect: () => void;
  sandbox?: boolean;
}) {
  const { t } = useTranslation();
  const LocationIcon = option.value === "cloud" ? Cloud : Laptop;
  return (
    <button
      type="button"
      aria-pressed={isActive}
      onClick={onSelect}
      className={`flex min-h-11 items-center gap-3 px-3 py-2.5 rounded-lg text-14 transition-colors text-left cursor-pointer hover:bg-theme-bg-subtle focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--theme-ring)] motion-reduce:transition-none${
        option.disabled ? " opacity-60" : ""
      }`}
      style={{
        background: isActive ? "var(--theme-bg-subtle)" : "transparent",
        color: "var(--theme-text)",
        border: sandbox
          ? `1px solid var(${
              isActive ? "--theme-border" : "--theme-border-faint"
            })`
          : undefined,
      }}
    >
      {sandbox ? (
        <LocationIcon
          size={18}
          className="shrink-0 text-theme-text-secondary"
          aria-hidden="true"
        />
      ) : (
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{
            background: isActive
              ? "var(--theme-primary)"
              : "var(--theme-border)",
          }}
        />
      )}
      <span className="min-w-0 flex-1">
        <span className={`block${sandbox ? " font-medium" : ""}`}>
          {option.label_key
            ? t(option.label_key)
            : option.label || String(option.value)}
        </span>
        {sandbox && (
          <span className="mt-0.5 block text-12 leading-relaxed text-theme-text-secondary">
            {t(`agentOptions.sandbox.${option.value}Hint`)}
          </span>
        )}
      </span>
      {sandbox ? (
        <span
          aria-hidden="true"
          className={`flex size-4 shrink-0 items-center justify-center rounded-full border ${
            isActive ? "border-theme-text-secondary" : "border-theme-border"
          }`}
        >
          {isActive && (
            <span className="size-2 rounded-full bg-theme-text-secondary" />
          )}
        </span>
      ) : (
        isActive && (
          <InteractiveIcon>
            <Check
              size={16}
              className="shrink-0 text-theme-text-secondary"
              aria-hidden="true"
            />
          </InteractiveIcon>
        )
      )}
    </button>
  );
}

export const AgentOptionButton = memo(function AgentOptionButton({
  optionKey,
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
    ? externalIsOpen ?? false
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
        {IconComponent ? (
          <IconComponent size={18} />
        ) : (
          <InteractiveIcon>
            <Settings size={18} />
          </InteractiveIcon>
        )}
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
            <InteractiveIcon>
              <ActiveIcon size={18} />
            </InteractiveIcon>
          </button>
        )}
        <ModalSurface
          open={showDropdown}
          onClose={() => setShowDropdown(false)}
          label={
            optionKey === "sandbox"
              ? t("agentOptions.sandbox.title")
              : description
          }
          className="modal-size-md"
        >
          <div
            className="w-full rounded-xl bg-theme-bg-card px-5 pt-4 pb-5 font-serif"
            style={{
              maxHeight: "60dvh",
              overflowY: "auto",
              overscrollBehavior: "contain",
            }}
          >
            <div className="mb-5 flex items-center justify-between gap-3">
              <h3 className="min-w-0 text-18 font-semibold text-theme-text">
                {optionKey === "sandbox"
                  ? t("agentOptions.sandbox.title")
                  : description}
              </h3>
              <DialogCloseButton onClick={() => setShowDropdown(false)} />
            </div>
            {note && (
              <div className="text-12 mb-3 px-2.5 py-1.5 rounded-lg bg-theme-bg-subtle text-theme-text-secondary">
                {note}
              </div>
            )}
            {optionKey === "sandbox" && (
              <h4 className="mb-2 text-12 font-medium text-theme-text-secondary">
                {t("agentOptions.sandbox.section")}
              </h4>
            )}
            <div
              role={optionKey === "sandbox" ? "group" : undefined}
              aria-label={
                optionKey === "sandbox"
                  ? t("agentOptions.sandbox.section")
                  : undefined
              }
              className="flex flex-col gap-2"
            >
              {options.map((opt) => (
                <AgentOptionRow
                  key={String(opt.value)}
                  option={opt}
                  isActive={opt.value === value}
                  sandbox={optionKey === "sandbox"}
                  onSelect={() => {
                    onChange(opt.value);
                    if (optionKey !== "sandbox") setShowDropdown(false);
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
      {IconComponent ? (
        <IconComponent size={18} />
      ) : (
        <InteractiveIcon>
          <Settings size={18} />
        </InteractiveIcon>
      )}
    </button>
  );
});
