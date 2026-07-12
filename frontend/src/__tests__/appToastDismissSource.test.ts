import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const appSource = readFileSync(resolve(import.meta.dirname, "../App.tsx"), {
  encoding: "utf8",
});

test("global toaster gives default toasts a dismiss button without wrapping custom toasts", () => {
  expect(appSource).toMatch(/ToastBar/);
  expect(appSource).toMatch(/currentToast\.type === "custom"/);
  expect(appSource).toMatch(/toast\.dismiss\(currentToast\.id\)/);
  expect(appSource).toMatch(/aria-label=\{t\("common\.dismiss"/);
  expect(appSource).toMatch(/flex w-full items-center gap-3 text-left/);
  expect(appSource).toMatch(
    /top:\s*"calc\(56px \+ var\(--app-safe-area-top, 0px\)\)"/,
  );
});
