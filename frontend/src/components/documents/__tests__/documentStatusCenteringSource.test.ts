import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(
  new URL("../DocumentPreviewContent.tsx", import.meta.url),
  "utf8",
);

test("document loading and error states fill the preview area for vertical centering", () => {
  for (const state of ["loading", "error"]) {
    const classes = source
      .match(
        new RegExp(
          `if \\(${state}\\) \\{\\s*return \\(\\s*<div className="([^"]+)"`,
        ),
      )?.[1]
      .split(" ");
    expect(classes).toEqual(
      expect.arrayContaining(["min-h-full", "items-center", "justify-center"]),
    );
  }
});

test("spreadsheet errors and empty sheets center within their available area", () => {
  const excel = readFileSync(
    new URL("../previews/ExcelPreview.tsx", import.meta.url),
    "utf8",
  );
  expect(excel).toMatch(
    /if \(error\)[\s\S]*?className="flex min-h-full items-center justify-center/,
  );
  expect(excel).toMatch(
    /totalRows === 0[\s\S]*?className="absolute inset-0 flex flex-col items-center justify-center/,
  );
});

test("channel instance empty state fills the panel body", () => {
  const channels = readFileSync(
    new URL("../../pages/ChannelsPage.tsx", import.meta.url),
    "utf8",
  );
  expect(channels).toMatch(
    /channelInstances.length === 0[\s\S]*?className="flex h-full flex-col items-center justify-center/,
  );
});
