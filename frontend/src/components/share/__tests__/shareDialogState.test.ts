import {
  shouldLoadRunsForShareType,
  shouldShowExistingSharesSkeleton,
} from "../shareDialogState";

test("does not load runs when dialog opens in full share mode", () => {
  expect(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "full",
      hasLoadedRuns: false,
      isLoadingRuns: false,
    }),
  ).toBe(false);
});

test("loads runs after switching to partial share mode", () => {
  expect(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "partial",
      hasLoadedRuns: false,
      isLoadingRuns: false,
    }),
  ).toBe(true);
});

test("does not reload runs while an existing request is in flight", () => {
  expect(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "partial",
      hasLoadedRuns: false,
      isLoadingRuns: true,
    }),
  ).toBe(false);
});

test("does not reload runs after they are already available", () => {
  expect(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "partial",
      hasLoadedRuns: true,
      isLoadingRuns: false,
    }),
  ).toBe(false);
});

test("does not show existing shares skeleton on initial load", () => {
  expect(
    shouldShowExistingSharesSkeleton({
      isLoading: true,
      hasLoadedShares: false,
    }),
  ).toBe(false);
});

test("can show existing shares skeleton after data has loaded once", () => {
  expect(
    shouldShowExistingSharesSkeleton({
      isLoading: true,
      hasLoadedShares: true,
    }),
  ).toBe(true);
});
