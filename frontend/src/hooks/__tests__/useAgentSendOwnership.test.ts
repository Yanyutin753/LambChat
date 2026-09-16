import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const source = readFileSync(resolve(__dirname, "../useAgent.ts"), "utf8");

test("sendMessage owns its flags via a send sequence that stop/supersede bumps", () => {
  // fetch-event-source 的 abort 是 resolve 而非 reject：被顶掉的旧发送
  // 必走 finally，不得重置新发送已置好的 isLoading/isSendingRef
  expect(source).toMatch(/const sendSeqRef = useRef\(0\);/);
  expect(source).toMatch(
    /const sendSeq = \+\+sendSeqRef\.current;\s*\n\s*const ownsSend = \(\) => sendSeqRef\.current === sendSeq;/,
  );
  expect(source).toContain("if (ownsSend()) {");
});

test("stopGeneration takes over the send sequence before resetting flags", () => {
  expect(source).toMatch(
    /sendSeqRef\.current \+= 1;\s*\n\s*submitInFlightRef\.current = false;/,
  );
});

test("superseded sends still settle their own optimistic assistant bubble", () => {
  // 旧发送的流被掐掉后不会再收到终态事件，finally 必须收尾自己的气泡，
  // 否则留下永久 isStreaming 的空气泡，输入框卡「运行中」
  const settleBody = source.match(
    /收尾自己的乐观助手气泡([\s\S]*?)if \(ownsSend\(\)\) \{/,
  )?.[1];
  expect(settleBody).toBeTruthy();
  expect(settleBody).toMatch(/clearAllLoadingStates\(m\.parts \|\| \[\]\)/);
});

test("supplementFollowUp defers only while the submit POST is in flight", () => {
  // isSendingRef 整个流式期间恒为 true，不能作为在途判定——只有 POST
  // 未被服务端受理时打断才会双提交
  expect(source).toMatch(/if \(submitInFlightRef\.current\) \{/);
  expect(source).toMatch(/const submitInFlightRef = useRef\(false\);/);
});

test("loadHistory restores its pre-clear snapshot when superseded with an empty list", () => {
  // 「先 setMessages([]) 后被发送判 stale 早退」会留下空列表 + 卡 loading
  expect(source).toMatch(/const messagesSnapshot = messagesRef\.current;/);
  expect(source).toMatch(
    /if \(messagesRef\.current\.length === 0\) setMessages\(messagesSnapshot\);/,
  );
});

test("sendMessage releases the history-loading flags it supersedes", () => {
  expect(source).toMatch(
    /historyAbortControllerRef\.current = null;\s*\n\s*setIsLoadingHistory\(false\);\s*\n\s*isLoadingHistoryRef\.current = false;/,
  );
});
