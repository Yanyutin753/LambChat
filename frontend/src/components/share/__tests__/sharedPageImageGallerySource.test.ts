import { readFileSync } from "node:fs";
import { join } from "node:path";

const sharedPageSource = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);

test("shared page mounts the session image gallery provider over its messages", () => {
  // 分享页没有挂 SessionImageGalleryProvider 时，reveal_file 图片卡片
  // 点击预览是静默 no-op（MessageImageGallery 只依赖该 context）。
  expect(sharedPageSource).toMatch(/<SessionImageGalleryProvider messages=\{messages\}>/);
});
