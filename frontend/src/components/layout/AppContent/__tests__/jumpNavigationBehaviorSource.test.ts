import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const readSource = (relativePath: string) =>
  readFileSync(resolve(process.cwd(), "src", relativePath), "utf8");

const chatViewSource = readSource("components/layout/AppContent/ChatView.tsx");
const outlineSource = readSource(
  "components/layout/AppContent/useChatOutline.tsx",
);

// 小地图（时间轴/大纲）跳转必须瞬时到位：Virtuoso 的 smooth
// scrollToIndex 在长虚拟列表上是「估算 → 平滑滚动 → 测量 → 修正」的
// 多段迭代，表现为长时间停顿后缓慢爬行。
test("timeline and outline navigation jump instantly instead of smooth-scrolling", () => {
  expect(chatViewSource).toMatch(
    /scrollToIndex\(\{\s*index: messageIndex,\s*behavior: "auto",\s*align: "start",\s*offset: -24,\s*\}\)/,
  );
  expect(outlineSource).toMatch(
    /scrollToIndex\(\{\s*index: messageIndex,\s*behavior: "auto",\s*align: "start",\s*\}\)/,
  );
  expect(outlineSource).not.toMatch(
    /scrollToIndex\(\{\s*index: messageIndex,\s*behavior: "smooth"/,
  );
});

// 时间轴跳转只允许一次权威滚动：scrollToIndex 自带测量修正与重试，
// 追加 rAF scrollIntoView 会在远距离条目上按过期布局二次滚动、冲过
// 目标一轮——表现为「点的是这轮，点亮落在下一轮」。
test("timeline navigation scrolls once with offset instead of a racing scrollIntoView", () => {
  const timelineNavigate = chatViewSource.slice(
    chatViewSource.indexOf("handleTimelineNavigate"),
  );
  expect(timelineNavigate).toMatch(/offset: -24/);
  expect(timelineNavigate).not.toMatch(/\.scrollIntoView\(/);
});
