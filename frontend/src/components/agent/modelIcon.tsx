import { getModelIconUrl, isMonochromeIcon } from "./modelIcon";

export function ModelIconImg({
  model,
  provider,
  size = 22,
}: {
  model: string;
  provider?: string;
  size?: number;
}) {
  const url = getModelIconUrl(model, provider);
  const mono = isMonochromeIcon(model, provider);
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
      className="flex items-center justify-center rounded-full bg-white dark:bg-stone-600"
      style={{ width: size, height: size }}
    >
      <img
        src={url}
        alt={model}
        width={size * 0.7}
        height={size * 0.7}
        className={mono ? "dark:invert" : ""}
      />
    </div>
  );
}
