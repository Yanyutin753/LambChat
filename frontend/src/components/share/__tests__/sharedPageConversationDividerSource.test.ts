import test from "node:test";
import assert from "node:assert/strict";
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

  assert.notEqual(dividerIndex, -1);
  assert.notEqual(messagesBranchIndex, -1);
  assert.ok(dividerIndex < messagesBranchIndex);
});
