import { readFileSync } from "node:fs";

/**
 * 图片画廊收起接线守卫：ChatMessage 必须把「消息是否流式生成」作为画廊
 * 默认展开态传入，且带稳定 stateKey——否则历史消息打开会话时图片全量
 * 铺开（产品要求：初次建立内容展开，回看收起）。
 */

function read(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf8");
}

test("ChatMessage wires galleries to stream-only auto expansion", () => {
  const source = read("../index.tsx");
  expect(source).toMatch(
    /<MessageImageGallery[^>]*defaultExpanded=\{message\.isStreaming\}/s,
  );
  expect(source).toMatch(
    /<MessageImageGallery[^>]*stateKey=\{`\$\{message\.id\}:gallery-\$\{group\.startPartIndex\}`\}/s,
  );
});

test("gallery expansion state rehydrates from the session uiExpansion store", () => {
  const source = read("../MessageImageGallery.tsx");
  expect(source).toContain("useUiExpansionState");
  // 挂载时把初次生成态钉进 store：流式结束后虚拟列表卸载复水不误收起
  expect(source).toMatch(/getUiExpansion\(stateKey\) === undefined/);
});
