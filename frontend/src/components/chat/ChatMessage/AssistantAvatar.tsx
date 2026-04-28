import { useState, useEffect } from "react";

const DEFAULT_ICON_SRC = "/icons/icon.svg";
let cachedDefaultDataUrl: string | null = null;
let pendingDefault: Promise<string> | null = null;

function loadDefaultDataUrl(): Promise<string> {
  if (cachedDefaultDataUrl) return Promise.resolve(cachedDefaultDataUrl);
  if (pendingDefault) return pendingDefault;
  pendingDefault = fetch(DEFAULT_ICON_SRC)
    .then((r) => r.text())
    .then((svg) => {
      cachedDefaultDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
        svg,
      )}`;
      pendingDefault = null;
      return cachedDefaultDataUrl;
    })
    .catch(() => {
      pendingDefault = null;
      return DEFAULT_ICON_SRC;
    });
  return pendingDefault;
}

loadDefaultDataUrl();

interface AssistantAvatarProps {
  className?: string;
  avatarUrl?: string | null;
  size?: number;
}

export function AssistantAvatar({
  className,
  avatarUrl,
  size = 28,
}: AssistantAvatarProps) {
  const [defaultSrc, setDefaultSrc] = useState(DEFAULT_ICON_SRC);

  useEffect(() => {
    loadDefaultDataUrl().then(setDefaultSrc);
  }, []);

  const src = avatarUrl || defaultSrc;

  return (
    <img
      src={src}
      alt="Assistant"
      width={size}
      height={size}
      className={className}
      onError={(e) => {
        if (avatarUrl) {
          (e.target as HTMLImageElement).src = defaultSrc;
        }
      }}
    />
  );
}
