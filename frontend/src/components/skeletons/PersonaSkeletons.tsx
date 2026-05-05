import { SkeletonLine } from "./primitives";
import { PanelHeaderSkeleton } from "./PanelHeaderSkeleton";

export function PersonaPlazaSkeleton() {
  return (
    <div className="flex h-full flex-col gap-4 animate-fade-in">
      <PanelHeaderSkeleton hasSearch />
      <div className="flex-1 overflow-y-auto min-h-0 p-3 sm:p-6 xl:p-8">
        <div className="grid auto-grid-cols gap-4 xl:gap-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="panel-card flex flex-col p-5">
              <div className="flex items-start gap-3">
                <div className="size-10 shrink-0 rounded-full skeleton-line" />
                <div className="min-w-0 flex-1">
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-3/4" : "w-1/2"}
                    className="!h-4"
                  />
                  <SkeletonLine width="w-full" className="!h-3 mt-2" />
                  <SkeletonLine
                    width={i % 2 === 0 ? "w-5/6" : "w-2/3"}
                    className="!h-3 mt-1.5"
                  />
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                <SkeletonLine width="w-14" className="!h-5 !rounded-full" />
                <SkeletonLine width="w-20" className="!h-5 !rounded-full" />
              </div>
              <div
                className="mt-4 flex gap-2 border-t pt-3"
                style={{ borderColor: "var(--theme-border)" }}
              >
                <SkeletonLine width="w-16" className="!h-8 !rounded-lg" />
                <SkeletonLine width="w-16" className="!h-8 !rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function PersonaPageSkeleton() {
  return (
    <div className="flex h-full animate-fade-in">
      <PersonaPlazaSkeleton />
    </div>
  );
}
