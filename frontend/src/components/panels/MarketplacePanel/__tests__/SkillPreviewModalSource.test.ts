import { readFileSync } from "node:fs";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("marketplace skill files open in a dedicated preview dialog", () => {
  const source = readSource("../SkillPreviewModal.tsx");

  expect(source).toMatch(/const \[previewFilePath, setPreviewFilePath\]/);
  expect(source).toMatch(/setPreviewFilePath\(filePath\)/);
  expect(source).toMatch(/previewFilePath &&/);
  expect(source).toMatch(/createPortal\(/);
  expect(source).toMatch(/fixed inset-0 z-\[1200\]/);
  expect(source).toMatch(/role="dialog"/);
  expect(source).toMatch(/aria-label=\{t\("marketplace\.closePreview"/);
  expect(source).toMatch(
    /import \{ SkillEditor \} from "..\/..\/skill\/SkillEditor"/,
  );
  expect(source).toMatch(
    /<SkillEditor[\s\S]*readOnly[\s\S]*lineWrapping=\{false\}/,
  );
  expect(source).toMatch(/className="flex-1 min-h-0"/);
  expect(source).not.toMatch(/DeferredCodeMirrorViewer/);
  expect(source).not.toMatch(/className="max-h-64"/);
});
