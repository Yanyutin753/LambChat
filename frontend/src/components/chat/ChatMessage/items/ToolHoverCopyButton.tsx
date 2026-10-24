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
    "absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity",
  panelRaised:
    "absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity z-10",
  panelCompact:
    "absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity",
  panelCompactRaised:
    "absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity z-10",
  result:
    "absolute top-1.5 right-1.5 opacity-0 group-hover/result:opacity-100 transition-opacity",
  resultCompact:
    "absolute top-0.5 right-0.5 opacity-0 group-hover/result:opacity-100 transition-opacity",
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
        "tool-hover-copy pointer-events-none group-hover:pointer-events-auto group-hover/result:pointer-events-auto focus-within:opacity-100 focus-within:pointer-events-auto motion-reduce:transition-none",
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
