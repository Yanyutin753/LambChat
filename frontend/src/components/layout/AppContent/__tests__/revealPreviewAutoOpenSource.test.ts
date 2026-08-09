import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("automatic reveal previews require an empty docked lane", () => {
  const hook = readFileSync(
    new URL("../useRevealPreview.ts", import.meta.url),
    "utf8",
  );

  expect(hook).toMatch(/shouldAllowAutomaticRightPanel/);
  expect(hook).toMatch(/hasOpenRightPanel/);
  expect(hook).toMatch(/source === "auto"/);
});

test("automatic reveal intent reaches file and project panel renderers", () => {
  const chatView = readFileSync(
    new URL("../ChatView.tsx", import.meta.url),
    "utf8",
  );
  const host = readFileSync(
    new URL(
      "../../../chat/ChatMessage/items/RevealPreviewHost.tsx",
      import.meta.url,
    ),
    "utf8",
  );
  const documentPreview = readFileSync(
    new URL("../../../documents/DocumentPreview.tsx", import.meta.url),
    "utf8",
  );

  expect(chatView).toMatch(/automatic=\{activePreviewAutomatic\}/);
  expect(host.match(/automatic=\{automatic\}/g)).toHaveLength(3);
  expect(documentPreview).toMatch(/automatic=\{state\.automatic\}/);
});
