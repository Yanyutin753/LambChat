import test from "node:test";
import assert from "node:assert/strict";
import {
  shouldLoadRunsForShareType,
  shouldShowExistingSharesSkeleton,
} from "../shareDialogState";

test("does not load runs when dialog opens in full share mode", () => {
  assert.equal(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "full",
      hasLoadedRuns: false,
      isLoadingRuns: false,
    }),
    false,
  );
});

test("loads runs after switching to partial share mode", () => {
  assert.equal(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "partial",
      hasLoadedRuns: false,
      isLoadingRuns: false,
    }),
    true,
  );
});

test("does not reload runs while an existing request is in flight", () => {
  assert.equal(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "partial",
      hasLoadedRuns: false,
      isLoadingRuns: true,
    }),
    false,
  );
});

test("does not reload runs after they are already available", () => {
  assert.equal(
    shouldLoadRunsForShareType({
      isOpen: true,
      shareType: "partial",
      hasLoadedRuns: true,
      isLoadingRuns: false,
    }),
    false,
  );
});

test("does not show existing shares skeleton on initial load", () => {
  assert.equal(
    shouldShowExistingSharesSkeleton({
      isLoading: true,
      hasLoadedShares: false,
    }),
    false,
  );
});

test("can show existing shares skeleton after data has loaded once", () => {
  assert.equal(
    shouldShowExistingSharesSkeleton({
      isLoading: true,
      hasLoadedShares: true,
    }),
    true,
  );
});
