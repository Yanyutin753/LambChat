/** @vitest-environment jsdom */
import { render } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { AttachmentPreview } from "../AttachmentPreview";
vi.mock("../ChatMessage/ImageWithSkeleton", () => ({
  ImageWithSkeleton: ({ src }: { src?: string }) => (
    <img src={src} alt="preview" />
  ),
}));
test("pending local videos retain their file icon instead of loading video bytes as an image", () => {
  const { container } = render(
    <AttachmentPreview
      attachments={[
        {
          id: "pending",
          name: "clip.mp4",
          type: "video",
          mimeType: "video/mp4",
          size: 10,
          url: "blob:pending-video",
          isUploading: true,
        },
      ]}
      onRemove={vi.fn()}
    />,
  );
  expect(container.querySelector("img")).toBeNull();
});
