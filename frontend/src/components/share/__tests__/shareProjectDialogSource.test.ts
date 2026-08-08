import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(currentDir, "../ShareProjectDialog.tsx"),
  "utf8",
);

test("uses the explicit share-project heading translation", () => {
  expect(source).toContain('t("sidebar.shareProject")');
});

test("explains the capped bulk selection for projects over the limit", () => {
  expect(source).toContain("sessions.length > PROJECT_SHARE_SESSION_LIMIT");
  expect(source).toContain('t("share.selectUpToLimit"');
});
