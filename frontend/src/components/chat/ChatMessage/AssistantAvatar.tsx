import { useState, useEffect } from "react";

const ICON_SRC = "/icons/icon.svg";
let cachedDataUrl: string | null = null;
let pending: Promise<string> | null = null;

function loadDataUrl(): Promise<string> {
  if (cachedDataUrl) return Promise.resolve(cachedDataUrl);
  if (pending) return pending;
  pending = fetch(ICON_SRC)
    .then((r) => r.text())
    .then((svg) => {
      cachedDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
        svg,
      )}`;
      pending = null;
      return cachedDataUrl;
    })
    .catch(() => {
      pending = null;
      return ICON_SRC;
    });
  return pending;
}

// Pre-fetch on module load
loadDataUrl();

export function AssistantAvatar({ className }: { className?: string }) {
  const [src, setSrc] = useState(ICON_SRC);

  useEffect(() => {
    loadDataUrl().then(setSrc);
  }, []);

  return (
    <img
      src={src}
      alt="Assistant"
      width={28}
      height={28}
      className={className}
    />
  );
}
