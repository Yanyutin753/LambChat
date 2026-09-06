import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(
  resolve(__dirname, "../FileRevealItem.tsx"),
  "utf8",
);

test("file_reveal 内联媒体加载失败时重试 ?proxy=true 应用代理", () => {
  // OSS 预签名地址不可达（如海外桶 + 大陆网络）时，直连 302 加载失败，
  // 需与文档预览面板一致：onError 后改走应用代理流式加载兜底
  expect(source).toMatch(
    /import \{ mediaProxyFallbackSrc \} from "\.\.\/\.\.\/\.\.\/documents\/documentFetchCache"/,
  );
  const retries =
    source.match(/mediaProxyFallbackSrc\(e\.currentTarget\)/g) ?? [];
  // <audio> 与 <video> 两个内联媒体元素都要接上
  expect(retries.length).toBeGreaterThanOrEqual(2);
});
