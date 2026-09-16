import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");

test("supplementFollowUp interrupts the running turn before resending", () => {
  // 补充当前问题 = 先优雅停止当前 run（复用取消链路），再立即把补充
  // 内容作为新消息发出：原问题与半截回答保留在历史，新一轮结合补充
  // 内容重新生成
  expect(source).toMatch(/const supplementFollowUp = useCallback/);
  expect(source).toMatch(/if \(!text && !attachments\?\.length\) return;/);
  expect(source).toMatch(
    /await stopGeneration\(\);\s*await sendMessageRef\.current\?\.\(text, attachments\);/,
  );
});

test("supplementFollowUp queues only while the submit POST is unresolved", () => {
  // 流式中 isSendingRef 恒为 true（await connectToSSE 贯穿全程），用它
  // 判在途会让回车补充永远变成排队；只有 POST 在途才需要转排队
  expect(source).toMatch(/if \(submitInFlightRef\.current\) \{/);
  expect(source).toMatch(/queueFollowUp\(text, attachments\);/);
});
