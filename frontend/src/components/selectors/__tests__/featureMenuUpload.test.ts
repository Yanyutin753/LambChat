import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const featureMenuSource = readFileSync(
  new URL("../FeatureMenu.tsx", import.meta.url),
  "utf8",
);

const toolbarSource = readFileSync(
  new URL("../../chat/ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);

test("feature menu uses one upload action instead of category upload items", () => {
  assert.match(featureMenuSource, /onUploadFiles: \(\) => void/);
  assert.match(
    featureMenuSource,
    /label=\{t\("featureMenu\.upload", "上传"\)\}/,
  );
  assert.match(featureMenuSource, /onClick=\{\(\) => \{\s*onUploadFiles\(\);/);
  assert.doesNotMatch(featureMenuSource, /uploadCategories\.map\(\(category\)/);
  assert.doesNotMatch(featureMenuSource, /FILE_CATEGORY_ICONS/);
});

test("chat input toolbar opens a combined file picker and lets upload auto-detect categories", () => {
  assert.match(toolbarSource, /const FILE_ACCEPT_ALL =/);
  assert.match(toolbarSource, /handleUploadFiles/);
  assert.match(
    toolbarSource,
    /fileInputRef\.current\.accept = getFileAccept\(uploadCategories\);/,
  );
  assert.match(toolbarSource, /uploadFiles\(files\);/);
  assert.doesNotMatch(
    toolbarSource,
    /uploadFiles\(files, selectedFileCategory/,
  );
});
