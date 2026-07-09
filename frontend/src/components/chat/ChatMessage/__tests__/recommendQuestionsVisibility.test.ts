import { readFileSync } from "node:fs";
const chatMessageSource = readFileSync(
  new URL("../index.tsx", import.meta.url),
  "utf8",
);

test("recommended questions wait for the completed assistant action bar", () => {
  expect(chatMessageSource).toMatch(
    /!\s*message\.isStreaming\s*&&\s*isLastMessage\s*&&\s*message\.parts\?\.some\(\(p\) => p\.type === "recommend_questions"\)/,
  );
});
