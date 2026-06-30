import test from "node:test";
import assert from "node:assert/strict";
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

  assert.deepEqual(
    items.map((item) => [item.id, item.src, item.alt, item.group]),
    [
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
    ],
  );

  assert.equal(items.filter((item) => item.group === "conversation").length, 3);
  assert.equal(items.filter((item) => item.group === "reveal-file").length, 1);
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

  assert.deepEqual(
    collectSessionImageGalleryItems(messages).map((item) => [
      item.id,
      item.src,
      item.alt,
      item.group,
    ]),
    [
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
    ],
  );
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

  assert.deepEqual(
    collectSessionImageGalleryItems(messages).map((item) => item.src),
    ["/api/upload/file/generated-images/cat.png"],
  );
});

test("ImageViewer follows the mobile visual viewport instead of the layout viewport", () => {
  const source = readFileSync(
    new URL("../../../common/ImageViewer.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /className="fixed inset-0 z-\[300\] flex flex-col/);
  assert.match(source, /height:\s*"var\(--app-viewport-height, 100dvh\)"/);
  assert.match(
    source,
    /transform:\s*"translate3d\(0, var\(--app-viewport-offset-top, 0px\), 0\)"/,
  );
});

test("ChatView provides a session image gallery around chat messages", () => {
  const source = readFileSync(
    new URL("../../../layout/AppContent/ChatView.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /SessionImageGalleryProvider/);
  assert.match(source, /messages=\{messages\}/);
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

  assert.match(markdownSource, /useSessionImageGallery/);
  assert.match(markdownSource, /sessionImageGallery\?\.openImage/);
  assert.match(
    markdownSource,
    /<ImageWithSkeleton[\s\S]*?\bloading="eager"/,
    "markdown images should be eager so browser captures do not keep skeleton placeholders",
  );
  assert.match(userBubbleSource, /useSessionImageGallery/);
  assert.match(userBubbleSource, /sessionImageGallery\?\.openImage/);
  assert.match(fileRevealSource, /useSessionImageGallery/);
  assert.match(fileRevealSource, /sessionImageGallery\?\.openImage/);
  assert.match(fileRevealSource, /group:\s*"reveal-file"/);
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

  assert.doesNotMatch(sessionGallerySource, /RevealArtifactsSummary/);
  assert.doesNotMatch(sessionGallerySource, /collectRevealArtifacts/);
  assert.doesNotMatch(sessionGallerySource, /buildRevealArtifactTree/);
  assert.doesNotMatch(
    sessionGallerySource,
    /getRevealArtifactImagePreviewItems/,
  );
  assert.doesNotMatch(sessionGallerySource, /from "\.\/revealArtifacts"/);

  assert.doesNotMatch(revealSummarySource, /useSessionImageGallery/);
  assert.doesNotMatch(revealSummarySource, /SessionImageGalleryProvider/);
  assert.doesNotMatch(revealSummarySource, /sessionImageGallery/);
});
