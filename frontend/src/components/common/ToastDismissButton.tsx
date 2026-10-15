import { X } from "lucide-react";
import { IconButton } from "./ui/IconButton";
import { topmostVisibleModalDialog } from "../../utils/modalDialog";

export function ToastDismissButton({
  label,
  onDismiss,
  className = "",
}: {
  label: string;
  onDismiss: () => void;
  className?: string;
}) {
  return (
    <IconButton
      size="sm"
      icon={<X size={14} aria-hidden="true" />}
      className={`app-toast-dismiss shrink-0 ${className}`}
      aria-label={label}
      onMouseDown={(event) => event.preventDefault()}
      onClick={(event) => {
        event.stopPropagation();
        if (document.activeElement === event.currentTarget)
          topmostVisibleModalDialog()?.focus({ preventScroll: true });
        onDismiss();
      }}
    />
  );
}
