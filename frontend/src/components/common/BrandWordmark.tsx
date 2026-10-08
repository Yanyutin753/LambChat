import { useId } from "react";

export interface BrandWordmarkProps {
  className?: string;
  decorative?: boolean;
  title?: string;
  width?: number | string;
}

export function BrandWordmark({
  className,
  decorative = false,
  title = "LambChat",
  width,
}: BrandWordmarkProps) {
  const titleId = useId();
  const accessibilityProps = decorative
    ? { "aria-hidden": true }
    : { role: "img", "aria-labelledby": titleId };

  return (
    <svg
      {...accessibilityProps}
      className={className}
      data-wordmark-style="text-only"
      width={width}
      viewBox="0 0 220 62"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {!decorative && <title id={titleId}>{title}</title>}
      <text
        x="110"
        y="31"
        fontFamily="Georgia, 'Times New Roman', serif"
        fontSize="41"
        fontWeight="800"
        letterSpacing="-1.4"
        textAnchor="middle"
        dominantBaseline="central"
        fill="currentColor"
      >
        LambChat
      </text>
    </svg>
  );
}
