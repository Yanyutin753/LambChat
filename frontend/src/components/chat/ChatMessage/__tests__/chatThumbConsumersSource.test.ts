import { readFileSync } from "node:fs";

/**
 * 聊天图片缩略图接入守卫：所有消息内图片渲染点都必须走 buildChatThumbUrl，
 * 点击放大的 URL 仍然是原图（查看器按需加载原图）。
 */

function read(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf8");
}

test("markdown 正文图片渲染缩略图、点击仍取原图", () => {
  const source = read("../MarkdownContent.tsx");
  expect(source).toMatch(/thumbSrc=\{buildChatThumbUrl\(resolvedSrc\)\}/);
  expect(source).toMatch(/openImage\(resolvedSrc/);
});

test("reveal_file 画廊与文件卡片渲染缩略图", () => {
  const gallery = read("../MessageImageGallery.tsx");
  expect(gallery).toMatch(/thumbSrc=\{buildChatThumbUrl\(image\.src\)\}/);
  expect(gallery).toMatch(/openImage\(image\.src/);

  const revealItem = read("../items/FileRevealItem.tsx");
  expect(revealItem).toMatch(/thumbSrc=\{buildChatThumbUrl\(parsed\.s3Url\)\}/);
  expect(revealItem).toMatch(/openImagePreview\(parsed\.s3Url\)/);
});

test("image_generate 参考图与结果图渲染缩略图", () => {
  const source = read("../items/ImageGenerateItem.tsx");
  expect(source.match(/buildChatThumbUrl/g)?.length).toBeGreaterThanOrEqual(4);
  expect(source).toMatch(/openImagePreview\(resolvedUrl\)/);
  expect(source).toMatch(/openImagePreview\(img\.url\)/);
});

test("附件卡片：图片缩略图 + 文件封面 + 图标兜底", () => {
  const source = read("../../../common/AttachmentCard.tsx");
  expect(source).toMatch(/buildChatThumbUrl\(attachmentUrl\)/);
  expect(source).toMatch(/buildFileCoverUrl\(attachmentUrl\)/);
  expect(source).toMatch(/isChatCoverableFile\(fileExt\)/);
  // 封面加载失败必须回退到文件图标（零流量兜底）
  expect(source).toMatch(/errorFallback=\{\s*<FileIcon/s);
});
