import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const chatViewSource = readFileSync(
  resolve(
    process.cwd(),
    "src",
    "components",
    "layout",
    "AppContent",
    "ChatView.tsx",
  ),
  "utf8",
);

test("chat scroller component identity never depends on the skeleton flag", () => {
  // components.Scroller identity changes make react-virtuoso remount the
  // scroller subtree and reset scroll to the first message. The completion
  // commit (streaming stops + "disconnected" while isLoading is still true)
  // toggles showStreamingFooterSkeleton, so that flag must stay out of the
  // Scroller's dependency array; only the Footer may follow it.
  const scrollerStart = chatViewSource.indexOf(
    "const virtuosoScrollerComponent = useCallback(",
  );
  const scrollerEnd = chatViewSource.indexOf(
    "\n  );",
    scrollerStart,
  );

  expect(scrollerStart).toBeGreaterThan(-1);
  expect(scrollerEnd).toBeGreaterThan(scrollerStart);

  const scrollerBlock = chatViewSource.slice(scrollerStart, scrollerEnd);
  expect(scrollerBlock).not.toMatch(/showStreamingFooterSkeleton/);
  expect(scrollerBlock).toMatch(
    /\[handleVirtuosoScrollerElementChange\],?\s*$/,
  );

  const componentsStart = chatViewSource.indexOf(
    "const virtuosoComponents = useMemo(",
  );
  const componentsEnd = chatViewSource.indexOf(
    "\n  );",
    componentsStart,
  );
  const componentsBlock = chatViewSource.slice(componentsStart, componentsEnd);
  expect(componentsStart).toBeGreaterThan(-1);
  expect(componentsBlock).toMatch(/Scroller: virtuosoScrollerComponent/);
  expect(componentsBlock).toMatch(/Footer: virtuosoFooterComponent/);
});
