import { readFileSync } from "node:fs";

function read(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

/**
 * ui-pro 刷新后的骨架同步守护：骨架必须镜像真实组件当前的
 * 行布局与实体名排版（font-serif / 收紧的工具栏间距），
 * 保证加载态 → 加载完成不发生结构或排版跳变。
 */

test("chat input toolbar skeleton mirrors current toolbar layout", () => {
  const toolbar = read("../../chat/ChatInputToolbar.tsx");
  const skeleton = read("../ChatSkeletons.tsx");

  // 真实工具栏：外层 gap-1、左簇 gap-0.5 sm:gap-1.5、右簇同轴居中 gap-1 sm:gap-1.5
  expect(toolbar).toMatch(/justify-between gap-1 px-2 pb-3 pt-3 mx-0\.5/);
  expect(toolbar).toMatch(/flex-1 items-center gap-0\.5 sm:gap-1\.5/);
  expect(toolbar).toMatch(/items-center gap-1 sm:gap-1\.5 self-center/);

  expect(skeleton).toMatch(/justify-between gap-1 px-2 pb-3 pt-3 mx-0\.5/);
  expect(skeleton).toMatch(/flex-1 items-center gap-0\.5 sm:gap-1\.5/);
  expect(skeleton).toMatch(/items-center gap-1 sm:gap-1\.5 self-center/);
  // 左簇不再设横向滚动容器（真实组件已移除，滚动会裁切 chip）
  expect(skeleton).not.toMatch(/overflow-x-auto/);
});

test("toolbar chip skeleton keeps the overflow-hidden truncation chain", () => {
  const skeleton = read("../ChatSkeletons.tsx");
  // 真实 ToolbarChip 包装类：chat-tool-btn group shrink min-w-0 overflow-hidden
  expect(skeleton).toMatch(
    /chat-tool-btn group shrink min-w-0 overflow-hidden/,
  );
});

test("sidebar skeleton renders serif session and project titles", () => {
  const source = read("../SidebarSkeleton.tsx");
  // 真实标题为 truncate text-13 font-serif（SessionItem / ProjectItem）；
  // 定时任务名不是实体名，保持 sans
  expect(
    source.match(/skeleton-line h-\[13px\] rounded-md flex-1 font-serif/g)
      ?.length,
  ).toBe(2);
});

test("users panel skeleton renders serif usernames and role tags", () => {
  const source = read("../AdminSkeletons.tsx");
  expect(source).toMatch(
    /flex items-center gap-3 w-28 xl:w-32 shrink-0 font-serif/,
  );
  expect(source).toMatch(/flex gap-1 w-20 xl:w-24 shrink-0 font-serif/);
  expect(source).toMatch(/!h-4 font-serif/);
  expect(source).toMatch(/mt-3 flex flex-wrap gap-1\.5 font-serif/);
});

test("segmented tabs skeleton mirrors serif tab labels", () => {
  const source = read("../PanelSkeletonHelpers.tsx");
  // 真实分段页签容器带 font-serif（AgentSection / ModelSection）
  expect(source).toMatch(
    /inline-grid grid-cols-2 rounded-lg border border-\[var\(--glass-border\)\] bg-\[var\(--glass-bg-subtle\)\] p-1 my-3 font-serif/,
  );
});

test("skill and persona card skeletons render serif titles", () => {
  const skill = read("../SkillSkeletons.tsx");
  expect(skill).toMatch(/!h-\[15px\] sm:!h-\[16px\] font-serif/);
  const persona = read("../PersonaSkeletons.tsx");
  expect(persona).toMatch(/!h-4 font-serif/);
});
