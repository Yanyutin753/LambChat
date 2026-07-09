import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../DocumentPreviewToolbar.tsx", import.meta.url),
  "utf8",
);

test("document preview toolbar compact mode observes the whole toolbar, not the action group", () => {
  const rootToolbar = source.match(
    /return \(\s*<div\s+ref=\{toolbarRef\}\s+className="(?<className>[^"]*border-b[^"]*)"/,
  );
  const actionGroup = source.match(
    /<div\s+ref=\{toolbarRef\}\s+className="(?<className>[^"]*relative z-10 shrink-0[^"]*)"/,
  );

  expect(rootToolbar).toBeTruthy();
  expect(actionGroup).toBe(null);
});
