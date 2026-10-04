import type { ButtonHTMLAttributes } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

type DialogCloseButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "children" | "className" | "style" | "type"
>;

/** One quiet, accessible close action for dialog and sheet headers. */
export function DialogCloseButton(props: DialogCloseButtonProps) {
  const { t } = useTranslation();
  return (
    <button
      aria-label={t("common.close")}
      {...props}
      type="button"
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg border-0 bg-transparent p-0 text-theme-text-secondary shadow-none transition-colors sm:size-8 [@media(pointer:coarse)]:size-11 enabled:hover:bg-theme-bg-subtle enabled:hover:text-theme-text enabled:active:bg-theme-bg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--theme-ring)] disabled:cursor-not-allowed disabled:opacity-40 motion-reduce:transition-none"
    >
      <X size={18} strokeWidth={1.75} aria-hidden="true" />
    </button>
  );
}
