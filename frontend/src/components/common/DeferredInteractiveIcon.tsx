import { Children, lazy, Suspense, type ReactNode } from "react";

const AnimatedIcon = lazy(() =>
  import("./InteractiveIcon")
    .then((module) => ({ default: module.InteractiveIcon }))
    // Decorative animation must not prevent an offline/error control from rendering.
    .catch(() => ({
      default: ({ children }: { children: ReactNode }) =>
        Children.toArray(children),
    })),
);

/** Keep startup controls visible without eagerly loading the animation registry. */
export function DeferredInteractiveIcon({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={children}>
      <AnimatedIcon>{children}</AnimatedIcon>
    </Suspense>
  );
}
