import { shouldInterceptFilePreviewLink } from "../revealPreviewLinks.ts";

test("intercepts relative file preview links", () => {
  expect(
    shouldInterceptFilePreviewLink("/api/upload/file/report.pdf", {
      currentOrigin: "https://chat.example.com",
    }),
  ).toBe(true);
});

test("intercepts same-origin absolute file preview links", () => {
  expect(
    shouldInterceptFilePreviewLink(
      "https://chat.example.com/files/report.pdf",
      {
        currentOrigin: "https://chat.example.com",
      },
    ),
  ).toBe(true);
});

test("does not intercept cross-origin absolute file preview links", () => {
  expect(
    shouldInterceptFilePreviewLink("https://cdn.example.com/files/report.pdf", {
      currentOrigin: "https://chat.example.com",
    }),
  ).toBe(false);
});
