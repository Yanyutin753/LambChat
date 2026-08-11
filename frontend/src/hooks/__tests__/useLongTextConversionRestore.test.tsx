/** @vitest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { MessageAttachment } from "../../types";
import { useLongTextConversion } from "../useLongTextConversion";

const longTextAttachment: MessageAttachment = {
  id: "long-text-1",
  key: "uploads/long-text.txt",
  name: "long-text.txt",
  type: "document",
  mimeType: "text/plain",
  size: 4096,
  fromLongText: true,
  localOriginalText: "the original long text",
};

test("legacy long-text restore removes only the local card and restores text", () => {
  const setInput = vi.fn();
  const setAttachments = vi.fn();
  const scheduleTextareaResize = vi.fn();
  const { result } = renderHook(() =>
    useLongTextConversion({
      setInput,
      setAttachments,
      uploadFiles: vi.fn(),
      validateCount: () => true,
      scheduleTextareaResize,
      expanded: false,
    }),
  );

  let restored = false;
  act(() => {
    restored = result.current.restoreLongTextAttachment(longTextAttachment);
  });

  expect(restored).toBe(true);
  const update = setAttachments.mock.calls[0]?.[0] as (
    previous: MessageAttachment[],
  ) => MessageAttachment[];
  expect(
    update([
      longTextAttachment,
      { ...longTextAttachment, id: "keep", key: "uploads/keep.txt" },
    ]).map((attachment) => attachment.id),
  ).toEqual(["keep"]);
  expect(setInput).toHaveBeenCalledWith("the original long text");
  expect(scheduleTextareaResize).toHaveBeenCalledOnce();
});
