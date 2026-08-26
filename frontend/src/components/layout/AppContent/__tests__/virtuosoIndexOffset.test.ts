import { describe, expect, test, vi } from "vitest";
import type { ListRange, VirtuosoHandle } from "react-virtuoso";
import {
  toDataIndex,
  translateVirtuosoRange,
  wrapVirtuosoHandleForDataIndices,
} from "../virtuosoIndexOffset";

describe("index translation", () => {
  test("converts virtuoso absolute indices back to data indices", () => {
    expect(toDataIndex(1_000_005, 1_000_000)).toBe(5);
    expect(toDataIndex(999_995, 999_990)).toBe(5);
  });

  test("translates a reported visible range back to data indices", () => {
    const range: ListRange = { startIndex: 1_000_003, endIndex: 1_000_011 };
    expect(translateVirtuosoRange(range, 1_000_000)).toEqual({
      startIndex: 3,
      endIndex: 11,
    });
  });

  test("clamps translated ranges at zero", () => {
    expect(
      translateVirtuosoRange(
        { startIndex: 999_998, endIndex: 1_000_004 },
        1_000_000,
      ),
    ).toEqual({ startIndex: 0, endIndex: 4 });
  });
});

describe("wrapVirtuosoHandleForDataIndices", () => {
  function makeHandle() {
    return {
      autoscrollToBottom: vi.fn(),
      getState: vi.fn(),
      scrollBy: vi.fn(),
      scrollIntoView: vi.fn(),
      scrollTo: vi.fn(),
      scrollToIndex: vi.fn(),
    } as unknown as VirtuosoHandle & {
      scrollToIndex: ReturnType<typeof vi.fn>;
    };
  }

  test("passes data indices to scrollToIndex unchanged", () => {
    // Virtuoso's scrollToIndex natively expects data indices even when
    // firstItemIndex is set; adding the offset would clamp every call to
    // the last item and scroll the chat to the bottom.
    const handle = makeHandle();
    const wrapped = wrapVirtuosoHandleForDataIndices(handle);

    wrapped.scrollToIndex(3);
    expect(handle.scrollToIndex).toHaveBeenCalledWith(3);

    wrapped.scrollToIndex({ index: 7, align: "center", behavior: "smooth" });
    expect(handle.scrollToIndex).toHaveBeenCalledWith({
      index: 7,
      align: "center",
      behavior: "smooth",
    });
  });

  test("passes through non-numeric locations like LAST untouched", () => {
    const handle = makeHandle();
    const wrapped = wrapVirtuosoHandleForDataIndices(handle);

    wrapped.scrollToIndex({ index: "LAST", align: "end" } as never);
    expect(handle.scrollToIndex).toHaveBeenCalledWith({
      index: "LAST",
      align: "end",
    });
  });

  test("keeps other handle methods available", () => {
    const handle = makeHandle();
    const wrapped = wrapVirtuosoHandleForDataIndices(handle);

    wrapped.scrollBy({ top: 100 });
    expect(handle.scrollBy).toHaveBeenCalledWith({ top: 100 });
  });
});
