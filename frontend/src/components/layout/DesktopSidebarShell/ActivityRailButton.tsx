import type { ComponentProps } from "react";
import { Tooltip } from "../../common/Tooltip";
import { useIconHover } from "@animateicons/react";
import type { MessageCircleIcon } from "@animateicons/react/lucide/message-circle-icon";

export function ActivityRailButton({
  icon: Icon,
  onClick,
  title,
  ...props
}: ComponentProps<"button"> & { icon: typeof MessageCircleIcon }) {
  const { ref, triggerProps } = useIconHover({ trigger: "both" });
  return (
    <Tooltip content={title ?? props["aria-label"]} placement="right">
      <button
        type="button"
        {...props}
        {...triggerProps}
        onClick={(event) => {
          triggerProps.onClick?.(event);
          onClick?.(event);
        }}
        onFocus={() => ref.current?.startAnimation()}
        onBlur={() => ref.current?.stopAnimation()}
      >
        <Icon
          ref={ref}
          size={19}
          className="size-[1.1875rem] [&>svg]:size-full"
          duration={0.7}
          aria-hidden="true"
        />
      </button>
    </Tooltip>
  );
}
