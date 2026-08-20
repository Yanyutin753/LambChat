import { readFileSync } from "node:fs";
const chatMessageSource = readFileSync(
  new URL("../index.tsx", import.meta.url),
  "utf8",
);

test("recommended questions wait for the completed assistant action bar", () => {
  expect(chatMessageSource).toMatch(
    /!\s*message\.isStreaming\s*&&\s*!isWaitingForHuman\s*&&\s*isLastMessage/,
  );
});

test("finish-only message actions stay hidden while waiting for ask-human", () => {
  expect(chatMessageSource).toMatch(
    /!message\.isStreaming\s*&&\s*!isWaitingForHuman/,
  );
});
