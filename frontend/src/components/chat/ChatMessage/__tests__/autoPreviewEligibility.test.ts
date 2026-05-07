import test from "node:test";
import assert from "node:assert/strict";
import {
  getLatestAutoPreviewTarget,
  getLatestChatAutoPreviewTarget,
} from "../autoPreviewEligibility.ts";

test("returns the latest reveal tool part when auto preview is allowed", () => {
  assert.deepEqual(
    getLatestChatAutoPreviewTarget({
      messages: [
        {
          id: "message-1",
          parts: [
            {
              type: "tool",
              name: "reveal_file",
              args: {},
              success: true,
              isPending: false,
              cancelled: false,
            },
          ],
        },
        {
          id: "message-2",
          parts: [
            {
              type: "tool",
              name: "reveal_project",
              args: {},
              success: true,
              isPending: false,
              cancelled: false,
            },
          ],
        },
      ],
      suppressAutoPreview: false,
    }),
    {
      messageId: "message-2",
      partIndex: 0,
    },
  );
});

test("suppresses session auto preview while external navigation preview has priority", () => {
  assert.equal(
    getLatestChatAutoPreviewTarget({
      messages: [
        {
          id: "message-1",
          parts: [
            {
              type: "tool",
              name: "reveal_file",
              args: {},
              success: true,
              isPending: false,
              cancelled: false,
            },
          ],
        },
      ],
      suppressAutoPreview: true,
    }),
    null,
  );
});

test("keeps the base latest auto preview lookup unchanged", () => {
  assert.deepEqual(
    getLatestAutoPreviewTarget([
      {
        id: "message-1",
        parts: [
          {
            type: "tool",
            name: "reveal_file",
            args: {},
            success: true,
            isPending: false,
            cancelled: false,
          },
        ],
      },
    ]),
    {
      messageId: "message-1",
      partIndex: 0,
    },
  );
});
