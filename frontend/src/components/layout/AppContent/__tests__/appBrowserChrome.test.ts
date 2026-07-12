import {
  getBrowserChromeNudgeScrollY,
  shouldNudgeBrowserChrome,
} from "../appBrowserChrome.ts";

test("nudges browser chrome only for direct mobile browser access", () => {
  expect(
    shouldNudgeBrowserChrome({
      isMobileDevice: true,
      isStandaloneDisplayMode: false,
      hasVisualViewport: true,
    }),
  ).toBe(true);
  expect(
    shouldNudgeBrowserChrome({
      isMobileDevice: true,
      isStandaloneDisplayMode: true,
      hasVisualViewport: true,
    }),
  ).toBe(false);
  expect(
    shouldNudgeBrowserChrome({
      isMobileDevice: false,
      isStandaloneDisplayMode: false,
      hasVisualViewport: true,
    }),
  ).toBe(false);
  expect(
    shouldNudgeBrowserChrome({
      isMobileDevice: true,
      isStandaloneDisplayMode: false,
      hasVisualViewport: false,
    }),
  ).toBe(false);
});

test("scrolls one pixel only when the page has a scroll runway", () => {
  expect(
    getBrowserChromeNudgeScrollY({
      scrollHeight: 801,
      innerHeight: 800,
    }),
  ).toBe(1);
  expect(
    getBrowserChromeNudgeScrollY({
      scrollHeight: 800,
      innerHeight: 800,
    }),
  ).toBe(0);
});
