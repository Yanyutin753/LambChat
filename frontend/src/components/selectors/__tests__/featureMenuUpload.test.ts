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
  expect(featureMenuSource).toMatch(
    /label=\{t\("featureMenu\.upload", "上传"\)\}/,
  );
  expect(featureMenuSource).toMatch(
    /onClick=\{\(\) => \{\s*onUploadFiles\(\);/,
  );
  expect(featureMenuSource).not.toMatch(/uploadCategories\.map\(\(category\)/);
  expect(featureMenuSource).not.toMatch(/FILE_CATEGORY_ICONS/);
});

test("chat input toolbar opens a combined file picker and lets upload auto-detect categories", () => {
  expect(toolbarSource).toMatch(/handleUploadFiles/);
  expect(toolbarSource).toMatch(
    /fileInputRef\.current\.accept = getFileAccept\(uploadCategories\);/,
  );
  expect(toolbarSource).toMatch(/uploadFiles\(files\);/);
  expect(toolbarSource).not.toMatch(/uploadFiles\(files, selectedFileCategory/);
});

test("chat input toolbar leaves accept empty when every category is permitted", () => {
  // Android 13+ 见 accept 含 image/* 即弹系统照片选择器，只能选图片；
  // 全类目放行时不设 accept（空串），让系统弹相册+文件管理器完整选择器。
  expect(toolbarSource).toMatch(/import \{ getFileAccept \} from "\.\/fileAccept";/);
  const fileAcceptSource = readFileSync(
    new URL("../../chat/fileAccept.ts", import.meta.url),
    "utf8",
  );
  expect(fileAcceptSource).toMatch(/ALL_FILE_CATEGORIES\.every/);
  expect(fileAcceptSource).not.toMatch(/FILE_ACCEPT_ALL/);
  expect(fileAcceptSource).not.toMatch(/Object\.values\(FILE_CATEGORY_ACCEPT\)/);
});
