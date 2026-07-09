import { readFileSync } from "node:fs";
const featureMenuSource = readFileSync(
  new URL("../FeatureMenu.tsx", import.meta.url),
  "utf8",
);

const toolbarSource = readFileSync(
  new URL("../../chat/ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);

test("feature menu uses one upload action instead of category upload items", () => {
  expect(featureMenuSource).toMatch(/onUploadFiles: \(\) => void/);
  expect(featureMenuSource).toMatch(/label=\{t\("featureMenu\.upload"/);
  expect(featureMenuSource).toMatch(
    /onClick=\{\(\) => \{\s*onUploadFiles\(\);/,
  );
  expect(featureMenuSource).not.toMatch(/uploadCategories\.map\(\(category\)/);
  expect(featureMenuSource).not.toMatch(/FILE_CATEGORY_ICONS/);
});

test("chat input toolbar opens a combined file picker and lets upload auto-detect categories", () => {
  expect(toolbarSource).toMatch(/const FILE_ACCEPT_ALL =/);
  expect(toolbarSource).toMatch(/handleUploadFiles/);
  expect(toolbarSource).toMatch(
    /fileInputRef\.current\.accept = getFileAccept\(uploadCategories\);/,
  );
  expect(toolbarSource).toMatch(/uploadFiles\(files\);/);
  expect(toolbarSource).not.toMatch(/uploadFiles\(files, selectedFileCategory/);
});
