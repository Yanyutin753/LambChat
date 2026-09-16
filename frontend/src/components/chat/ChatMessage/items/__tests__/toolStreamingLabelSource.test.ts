import { readFileSync } from "node:fs";

// 所有工具 item 进行中统一走 useToolStreamingLabel：标签像「思考中」一样
// 流式追加正在生成的参数尾部 + 打字点动画，不再单调。

const toolItems = [
  "../ReadFileItem.tsx",
  "../EditFileItem.tsx",
  "../WriteFileItem.tsx",
  "../GrepItem.tsx",
  "../LsItem.tsx",
  "../GlobItem.tsx",
  "../ExecuteItem.tsx",
  "../EvalItem.tsx",
  "../ImageGenerateItem.tsx",
  "../ImageAnalyzeItem.tsx",
  "../UploadUrlToSandboxItem.tsx",
  "../TransferItem.tsx",
  "../AudioTranscribeItem.tsx",
  "../DocumentParseItem.tsx",
  "../ScheduledTaskItem.tsx",
  "../EnvVarItem.tsx",
  "../PersonaItem.tsx",
  "../TeamItem.tsx",
  "../MemoryRecallItem.tsx",
  "../MemoryStoreItem.tsx",
  "../AskHumanItem.tsx",
  "../ToolSearchItem.tsx",
  "../ConversationHistoryItem.tsx",
  "../SkillSearchItem.tsx",
  "../../ToolCallItem.tsx",
];

describe.each(toolItems)("streaming pill label: %s", (file) => {
  test("streams generating args into the pill label while pending", () => {
    const source = readFileSync(new URL(file, import.meta.url), "utf8");

    // 统一机制：进行中把正在生成的参数尾部追加到标签
    expect(source).toMatch(/useToolStreamingLabel\(/);
    // 进行中带打字点动画
    expect(source).toMatch(/animatedDots=\{isStreamingLabel\}/);
  });
});
