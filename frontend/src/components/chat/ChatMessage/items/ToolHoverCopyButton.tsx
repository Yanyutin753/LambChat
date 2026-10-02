import { CopyButton } from "../../../common";
import { clsx } from "clsx";

type ToolHoverCopyPosition =
  | "panel"
  | "panelRaised"
  | "panelCompact"
  | "panelCompactRaised"
  | "result"
  | "resultCompact";

const positionClasses: Record<ToolHoverCopyPosition, string> = {
  panel:
    "absolute top-2 right-2 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity",
  panelRaised:
    "absolute top-2 right-2 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10",
  panelCompact:
    "absolute top-1 right-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity",
  panelCompactRaised:
    "absolute top-1 right-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10",
  result:
    "absolute top-1.5 right-1.5 sm:opacity-0 sm:group-hover/result:opacity-100 transition-opacity",
  resultCompact: "absolute top-0.5 right-0.5 transition-opacity",
};

export function ToolHoverCopyButton({
  text,
  size = 12,
  position,
  copyButtonClassName,
  className,
  hidden = false,
}: {
  text: string;
  size?: number;
  position: ToolHoverCopyPosition;
  copyButtonClassName?: string;
  className?: string;
  hidden?: boolean;
}) {
  return (
    <div
      className={clsx(
        positionClasses[position],
        "focus-within:opacity-100",
        className,
      )}
      onClick={(event) => event.stopPropagation()}
    >
      {!hidden && (
        <CopyButton text={text} size={size} className={copyButtonClassName} />
      )}
    </div>
  );
}
