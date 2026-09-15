export function getHeroSectionClassName(): string {
  return [
    "blog-hero",
    "relative",
    "flex",
    "min-h-[calc(100svh-var(--titlebar-inset,0px))]",
    "min-h-[calc(100dvh-var(--titlebar-inset,0px))]",
    "flex-col",
    "items-center",
    "justify-center",
    "overflow-hidden",
    "px-4",
    "pt-[calc(5rem+var(--app-safe-area-top,0px))]",
    "pb-20",
    "text-center",
    "sm:px-6",
    "sm:pt-28",
    "sm:pb-20",
  ].join(" ");
}
