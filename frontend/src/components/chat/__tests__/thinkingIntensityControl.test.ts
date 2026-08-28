import { readFileSync } from "node:fs";

const selectorsSource = readFileSync(
  new URL("../ChatInputSelectors.tsx", import.meta.url),
  "utf8",
);
const optionButtonSource = readFileSync(
  new URL("../AgentOptionButton.tsx", import.meta.url),
  "utf8",
);
const useAgentOptionsSource = readFileSync(
  new URL("../../layout/AppContent/useAgentOptions.ts", import.meta.url),
  "utf8",
);

test("thinking control is hidden for models without thinking support", () => {
  // 按模型能力显隐：仅后端下发 supports_thinking=false 时隐藏，未知时保留
  expect(selectorsSource).toMatch(/modelSupportsThinking !== false/);
});

test("thinking picker uses a plain option list, not a stepped slider", () => {
  // VS Code / Cherry Studio 风格：朴素单选列表；分档彩色滑块已移除
  expect(optionButtonSource).not.toMatch(/stepped-slider/);
  expect(optionButtonSource).not.toMatch(/role="slider"/);
  expect(optionButtonSource).not.toMatch(/THINKING_LEVEL_COLOR/);
});

test("thinking level tiers exclude the retired off option", () => {
  // "off" 档已下线：兜底档位只有 low/medium/high/max，历史 off 值归一为 low
  expect(useAgentOptionsSource).not.toMatch(/"off", label_key/);
  expect(useAgentOptionsSource).toMatch(
    /\["off", "disabled", "disable", "none"\]/,
  );
});
