import React, { useMemo } from "react";
import { getModelIconUrl } from "./modelIcon";

export const ModelIconImg = React.memo(function ModelIconImg({
  model,
  provider,
  size = 22,
}: {
  model: string;
  provider?: string;
  size?: number;
}) {
  const url = useMemo(
    () => getModelIconUrl(model, provider),
    [model, provider],
  );
  if (!url) {
    return (
      <div
        className="flex items-center justify-center rounded-full bg-stone-200 dark:bg-stone-600"
        style={{ width: size, height: size }}
      >
        <span className="text-xs font-bold text-stone-600 dark:text-stone-200">
          {model.charAt(0).toUpperCase()}
        </span>
      </div>
    );
  }
  return (
    <div
      className="flex items-center justify-center rounded-full bg-stone-50 dark:bg-stone-300/70 dark:ring-1 dark:ring-white/10"
      style={{ width: size, height: size }}
    >
      <img src={url} alt={model} width={size * 0.7} height={size * 0.7} />
    </div>
  );
});
