import * as LucideIcons from "lucide-react";

// Dynamic icon renderer - supports both lucide icons and emojis
export function DynamicIcon({
  name,
  size,
  className,
  fill,
}: {
  name?: string;
  size?: number;
  className?: string;
  fill?: string;
}) {
  if (!name)
    return (
      <span className={className} style={{ fontSize: size }}>
        📁
      </span>
    );
  if (name === "Star") {
    return (
      <span className={className} style={{ fontSize: size }}>
        ⭐
      </span>
    );
  }
  // Check if it's an emoji (non-ASCII character, or no ASCII letters)
  const isEmoji = !/^[a-zA-Z]+$/.test(name);
  if (isEmoji) {
    return (
      <span className={className} style={{ fontSize: size }}>
        {name}
      </span>
    );
  }
  const IconComponent = (
    LucideIcons as unknown as Record<
      string,
      React.ComponentType<{ size?: number; className?: string; fill?: string }>
    >
  )[name];
  return IconComponent ? (
    <IconComponent size={size} className={className} fill={fill} />
  ) : (
    <span
      className={className}
      style={{ fontSize: size ? size * 0.9 : undefined }}
    >
      📁
    </span>
  );
}
