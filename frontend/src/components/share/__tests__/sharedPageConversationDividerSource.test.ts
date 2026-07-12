import { readFileSync } from "node:fs";
import { join } from "node:path";

const sharedPageSource = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);

test("shared page keeps the conversation divider outside the message state branches", () => {
  const dividerIndex = sharedPageSource.indexOf(
    "data-share-conversation-divider",
  );
  const messagesBranchIndex = sharedPageSource.indexOf(
    "{messages.length === 0 ?",
  );

  expect(dividerIndex).not.toBe(-1);
  expect(messagesBranchIndex).not.toBe(-1);
  expect(dividerIndex < messagesBranchIndex).toBeTruthy();
});
