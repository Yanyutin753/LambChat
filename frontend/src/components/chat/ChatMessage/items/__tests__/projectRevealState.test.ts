import {
  countProjectRevealFiles,
  shouldLoadProjectRevealFiles,
} from "../projectRevealState.ts";

test("counts text and binary reveal_project files together", () => {
  expect(
    countProjectRevealFiles(
      {
        "/index.html": '<img src="/main.png">',
      },
      {
        "/main.png": "https://example.com/main.png",
        "/detail.png": "https://example.com/detail.png",
      },
    ),
  ).toBe(3);
});

test("counts pure binary reveal_project folders", () => {
  expect(
    countProjectRevealFiles(
      {},
      {
        "/main.png": "https://example.com/main.png",
        "/detail.png": "https://example.com/detail.png",
        "/flatlay.png": "https://example.com/flatlay.png",
      },
    ),
  ).toBe(3);
});

test("loads versioned project files only when preview work is actually needed", () => {
  expect(
    shouldLoadProjectRevealFiles({
      isVersionedProject: true,
      success: true,
      isPreviewOpen: false,
      allowAutoPreview: false,
    }),
  ).toBe(false);

  expect(
    shouldLoadProjectRevealFiles({
      isVersionedProject: true,
      success: true,
      isPreviewOpen: true,
      allowAutoPreview: false,
    }),
  ).toBe(true);

  expect(
    shouldLoadProjectRevealFiles({
      isVersionedProject: true,
      success: true,
      isPreviewOpen: false,
      allowAutoPreview: true,
    }),
  ).toBe(true);
});
