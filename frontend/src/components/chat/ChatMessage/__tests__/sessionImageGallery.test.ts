import { readFileSync } from "node:fs";
import { collectSessionImageGalleryItems } from "../sessionImageGallery.tsx";
import type { Message } from "../../../../types";

function createMessage(overrides: Partial<Message>): Message {
  return {
    id: overrides.id ?? "message-1",
    role: overrides.role ?? "assistant",
    content: overrides.content ?? "",
    timestamp: overrides.timestamp ?? new Date("2026-05-17T00:00:00.000Z"),
    ...overrides,
  };
}

test("collects session images from attachments, markdown, and individual reveal_file cards in message order", () => {
  const messages: Message[] = [
    createMessage({
      id: "user-1",
      role: "user",
      content: "look ![inline](/inline-user.png)",
      attachments: [
        {
          id: "attachment-image",
          key: "uploads/attachment.png",
          name: "attachment.png",
          type: "image",
          mimeType: "image/png",
          size: 12,
          url: "/attachment.png",
        },
        {
          id: "attachment-pdf",
          key: "uploads/file.pdf",
          name: "file.pdf",
          type: "document",
          mimeType: "application/pdf",
          size: 34,
          url: "/file.pdf",
        },
      ],
    }),
    createMessage({
      id: "assistant-1",
      role: "assistant",
      content: "",
      parts: [
        {
          type: "text",
          content: "rendered ![chart](/chart.png)",
        },
        {
          type: "tool",
          name: "reveal_file",
          success: true,
          args: { path: "/tmp/generated.png" },
          result: JSON.stringify({
            key: "revealed/generated.png",
            url: "/generated.png",
            name: "generated.png",
            type: "image",
            mimeType: "image/png",
            size: 56,
            _meta: { path: "/tmp/generated.png" },
          }),
        },
      ],
    }),
  ];

  const items = collectSessionImageGalleryItems(messages);

  expect(
    items.map((item) => [item.id, item.src, item.alt, item.group]),
  ).toEqual([
    [
      "user-1:attachment:attachment-image",
      "/attachment.png",
      "attachment.png",
      "conversation",
    ],
    ["user-1:content:image:0", "/inline-user.png", "inline", "conversation"],
    ["assistant-1:part:0:image:0", "/chart.png", "chart", "conversation"],
    [
      "assistant-1:part:1:reveal-file",
      "/generated.png",
      "generated.png",
      "reveal-file",
    ],
  ]);

  expect(items.filter((item) => item.group === "conversation").length).toBe(3);
  expect(items.filter((item) => item.group === "reveal-file").length).toBe(1);
});

test("collects generated image tool results for correct preview navigation", () => {
  const messages: Message[] = [
    createMessage({
      id: "assistant-generated",
      role: "assistant",
      parts: [
        {
          type: "tool",
          name: "image_generate",
          success: true,
          args: { prompt: "orange cat in sunlight" },
          result: JSON.stringify({
            success: true,
            images: [
              {
                url: "/api/upload/file/generated-images/cat-1.png",
                content_type: "image/png",
              },
              {
                url: "/api/upload/file/generated-images/cat-2.png",
                content_type: "image/png",
              },
            ],
          }),
        },
      ],
    }),
  ];

  expect(
    collectSessionImageGalleryItems(messages).map((item) => [
      item.id,
      item.src,
      item.alt,
      item.group,
    ]),
  ).toEqual([
    [
      "assistant-generated:part:0:generated-image:0",
      "/api/upload/file/generated-images/cat-1.png",
      "cat-1.png",
      "conversation",
    ],
    [
      "assistant-generated:part:0:generated-image:1",
      "/api/upload/file/generated-images/cat-2.png",
      "cat-2.png",
      "conversation",
    ],
  ]);
});

test("deduplicates images collected from markdown, attachments, and generated image results", () => {
  const messages: Message[] = [
    createMessage({
      id: "user-with-attachment",
      role: "user",
      content:
        "same image ![inline](/api/upload/file/generated-images/cat.png)",
      attachments: [
        {
          id: "attachment-image",
          key: "generated-images/cat.png",
          name: "cat.png",
          type: "image",
          mimeType: "image/png",
          size: 12,
          url: "/api/upload/file/generated-images/cat.png",
        },
      ],
    }),
    createMessage({
      id: "assistant-generated",
      role: "assistant",
      parts: [
        {
          type: "tool",
          name: "image_generate",
          success: true,
          args: { prompt: "orange cat in sunlight" },
          result: JSON.stringify({
            success: true,
            images: [
              {
                url: "/api/upload/file/generated-images/cat.png",
                content_type: "image/png",
              },
            ],
          }),
        },
      ],
    }),
  ];

  expect(
    collectSessionImageGalleryItems(messages).map((item) => item.src),
  ).toEqual(["/api/upload/file/generated-images/cat.png"]);
});

test("ImageViewer follows the mobile visual viewport instead of the layout viewport", () => {
  const source = readFileSync(
    new URL("../../../common/ImageViewer.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/className="fixed inset-0 z-\[300\] flex flex-col/);
  expect(source).toMatch(/height:\s*"var\(--app-viewport-height, 100dvh\)"/);
  expect(source).toMatch(
    /transform:\s*"translate3d\(0, var\(--app-viewport-offset-top, 0px\), 0\)"/,
  );
});

test("ChatView provides a session image gallery around chat messages", () => {
  const source = readFileSync(
    new URL("../../../layout/AppContent/ChatView.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/SessionImageGalleryProvider/);
  expect(source).toMatch(/messages=\{messages\}/);
});

test("conversation image entry points use the session gallery when available", () => {
  const markdownSource = readFileSync(
    new URL("../MarkdownContent.tsx", import.meta.url),
    "utf8",
  );
  const userBubbleSource = readFileSync(
    new URL("../UserMessageBubble.tsx", import.meta.url),
    "utf8",
  );
  const fileRevealSource = readFileSync(
    new URL("../items/FileRevealItem.tsx", import.meta.url),
    "utf8",
  );

  expect(markdownSource).toMatch(/useSessionImageGallery/);
  expect(markdownSource).toMatch(/sessionImageGallery\?\.openImage/);
  expect(markdownSource).toMatch(/<ImageWithSkeleton[\s\S]*?\bloading="eager"/);
  expect(userBubbleSource).toMatch(/useSessionImageGallery/);
  expect(userBubbleSource).toMatch(/sessionImageGallery\?\.openImage/);
  expect(fileRevealSource).toMatch(/useSessionImageGallery/);
  expect(fileRevealSource).toMatch(/sessionImageGallery\?\.openImage/);
  expect(fileRevealSource).toMatch(/group:\s*"reveal-file"/);
});

test("session image count includes reveal_file cards but not the RevealArtifactsSummary gallery", () => {
  const sessionGallerySource = readFileSync(
    new URL("../sessionImageGallery.tsx", import.meta.url),
    "utf8",
  );
  const revealSummarySource = readFileSync(
    new URL("../RevealArtifactsSummary.tsx", import.meta.url),
    "utf8",
  );

  expect(sessionGallerySource).not.toMatch(/RevealArtifactsSummary/);
  expect(sessionGallerySource).not.toMatch(/collectRevealArtifacts/);
  expect(sessionGallerySource).not.toMatch(/buildRevealArtifactTree/);
  expect(sessionGallerySource).not.toMatch(
    /getRevealArtifactImagePreviewItems/,
  );
  expect(sessionGallerySource).not.toMatch(/from "\.\/revealArtifacts"/);

  expect(revealSummarySource).not.toMatch(/useSessionImageGallery/);
  expect(revealSummarySource).not.toMatch(/SessionImageGalleryProvider/);
  expect(revealSummarySource).not.toMatch(/sessionImageGallery/);
});
