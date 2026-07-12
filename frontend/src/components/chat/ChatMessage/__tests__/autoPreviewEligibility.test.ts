import {
  getLatestAutoPreviewTarget,
  getLatestChatAutoPreviewTarget,
  getLatestObservedCompletionAutoPreviewTarget,
  getLatestObservedCompletionRevealPreviewRequest,
} from "../autoPreviewEligibility.ts";

test("returns the latest reveal tool part when auto preview is allowed", () => {
  expect(
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
  ).toEqual({
    messageId: "message-2",
    partIndex: 0,
  });
});

test("suppresses session auto preview while external navigation preview has priority", () => {
  expect(
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
  ).toBe(null);
});

test("keeps the base latest auto preview lookup unchanged", () => {
  expect(
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
  ).toEqual({
    messageId: "message-1",
    partIndex: 0,
  });
});

test("returns the latest artifact part for chat auto preview", () => {
  expect(
    getLatestChatAutoPreviewTarget({
      messages: [
        {
          id: "message-1",
          parts: [
            {
              type: "artifact",
              success: true,
              artifact: {
                kind: "file",
                id: "file:revealed/report.pdf",
                name: "report.pdf",
                path: "/workspace/report.pdf",
                preview: {
                  kind: "file",
                  previewKey: "revealed/report.pdf",
                  filePath: "/workspace/report.pdf",
                },
              },
            },
          ],
        },
      ],
      suppressAutoPreview: false,
    }),
  ).toEqual({
    messageId: "message-1",
    partIndex: 0,
  });
});

test("does not auto preview historical reveal results until a streaming message completes", () => {
  const messages = [
    {
      id: "historical-message",
      parts: [
        {
          type: "tool" as const,
          name: "reveal_project",
          args: {},
          success: true,
          isPending: false,
          cancelled: false,
        },
      ],
    },
    {
      id: "completed-after-streaming",
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: {},
          success: true,
          isPending: false,
          cancelled: false,
        },
      ],
    },
  ];

  expect(
    getLatestObservedCompletionAutoPreviewTarget({
      messages,
      observedStreamingMessageIds: new Set(),
    }),
  ).toBe(null);

  expect(
    getLatestObservedCompletionAutoPreviewTarget({
      messages,
      observedStreamingMessageIds: new Set(["completed-after-streaming"]),
    }),
  ).toEqual({
    messageId: "completed-after-streaming",
    partIndex: 0,
  });
});

test("allows the latest reveal from the current run even if streaming was not observed", () => {
  expect(
    getLatestObservedCompletionAutoPreviewTarget({
      messages: [
        {
          id: "historical-message",
          runId: "run-history",
          parts: [
            {
              type: "tool" as const,
              name: "reveal_project",
              args: {},
              success: true,
              isPending: false,
              cancelled: false,
            },
          ],
        },
        {
          id: "current-run-message",
          runId: "run-current",
          parts: [
            {
              type: "tool" as const,
              name: "reveal_file",
              args: {},
              success: true,
              isPending: false,
              cancelled: false,
            },
          ],
        },
      ],
      observedStreamingMessageIds: new Set(),
      currentRunId: "run-current",
    }),
  ).toEqual({
    messageId: "current-run-message",
    partIndex: 0,
  });
});

test("finds the latest nested reveal preview request from the current run", () => {
  const preview = getLatestObservedCompletionRevealPreviewRequest({
    messages: [
      {
        id: "current-run-message",
        runId: "run-current",
        parts: [
          {
            type: "subagent" as const,
            agent_id: "agent-1",
            agent_name: "builder",
            input: "create report",
            depth: 1,
            parts: [
              {
                type: "tool" as const,
                name: "reveal_file",
                args: {},
                success: true,
                isPending: false,
                cancelled: false,
                result: {
                  key: "revealed/report.pdf",
                  url: "/api/upload/file/revealed/report.pdf",
                  name: "report.pdf",
                  type: "document",
                  mimeType: "application/pdf",
                  size: 2048,
                  _meta: {
                    path: "/workspace/report.pdf",
                  },
                },
              },
            ],
          },
        ],
      },
    ],
    observedStreamingMessageIds: new Set(),
    currentRunId: "run-current",
  });

  expect(preview).toEqual({
    kind: "file",
    previewKey: "revealed/report.pdf",
    filePath: "/workspace/report.pdf",
    s3Key: "revealed/report.pdf",
    signedUrl: "/api/upload/file/revealed/report.pdf",
    fileSize: 2048,
  });
});

test("returns image file reveal preview requests for latest-file auto preview", () => {
  const preview = getLatestObservedCompletionRevealPreviewRequest({
    messages: [
      {
        id: "current-run-message",
        runId: "run-current",
        parts: [
          {
            type: "tool" as const,
            name: "reveal_file",
            args: {},
            success: true,
            isPending: false,
            cancelled: false,
            result: {
              key: "revealed/chart.png",
              url: "/api/upload/file/revealed/chart.png",
              name: "chart.png",
              type: "image",
              mimeType: "image/png",
              size: 4096,
              _meta: {
                path: "/workspace/chart.png",
              },
            },
          },
        ],
      },
    ],
    observedStreamingMessageIds: new Set(),
    currentRunId: "run-current",
  });

  expect(preview).toEqual({
    kind: "file",
    previewKey: "revealed/chart.png",
    filePath: "/workspace/chart.png",
    s3Key: "revealed/chart.png",
    signedUrl: "/api/upload/file/revealed/chart.png",
    fileSize: 4096,
  });
});

test("can return the latest historical reveal preview request after history has loaded", () => {
  const messages = [
    {
      id: "historical-message",
      runId: "run-history",
      parts: [
        {
          type: "tool" as const,
          name: "reveal_file",
          args: {},
          success: true,
          isPending: false,
          cancelled: false,
          result: {
            key: "revealed/application.md",
            url: "/api/upload/file/revealed/application.md",
            name: "application.md",
            type: "document",
            mimeType: "text/markdown",
            size: 2134,
            _meta: {
              path: "/home/user/application.md",
            },
          },
        },
      ],
    },
  ];

  expect(
    getLatestObservedCompletionRevealPreviewRequest({
      messages,
      observedStreamingMessageIds: new Set(),
    }),
  ).toBe(null);

  expect(
    getLatestObservedCompletionRevealPreviewRequest({
      messages,
      observedStreamingMessageIds: new Set(),
      allowHistoricalLatest: true,
    }),
  ).toEqual({
    kind: "file",
    previewKey: "revealed/application.md",
    filePath: "/home/user/application.md",
    s3Key: "revealed/application.md",
    signedUrl: "/api/upload/file/revealed/application.md",
    fileSize: 2134,
  });
});
