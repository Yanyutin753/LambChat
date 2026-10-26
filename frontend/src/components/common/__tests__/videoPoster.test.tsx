/** @vitest-environment jsdom */
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
vi.mock("../../../hooks/useUploadFileUrl", () => ({
  useUploadFileUrl: (src?: string) => ({ src, failed: false }),
}));
import { VideoWithPoster } from "../VideoWithPoster";
test("all players can display the stored poster without loading video frames", () => {
  render(
    <VideoWithPoster
      src="/api/upload/file/video/me/a.mp4"
      aria-label="clip"
      controls
    />,
  );
  const video = screen.getByLabelText("clip");
  expect(video.getAttribute("poster")).toBe(
    "/api/upload/file/video/me/a.mp4?cover=1",
  );
  expect(video.getAttribute("preload")).toBe("none");
});
