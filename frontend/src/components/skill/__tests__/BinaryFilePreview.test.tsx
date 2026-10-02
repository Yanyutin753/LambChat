/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BinaryFilePreview } from "../BinaryFilePreview";
import i18n from "../../../i18n";

afterEach(cleanup);
test("skill image preview has a native button that opens the viewer after loading", () => {
  render(
    <BinaryFilePreview
      url="/report.webp"
      mime_type="image/webp"
      size={100}
      fileName="report.webp"
    />,
  );
  fireEvent.load(screen.getByRole("img", { name: "report.webp" }));
  const preview = screen.getByRole("button", {
    name: "report.webp",
    exact: true,
  });
  expect(preview.tagName).toBe("BUTTON");
  fireEvent.click(preview);
  expect(
    screen.getByRole("dialog", { name: "report.webp", exact: true }),
  ).toBeInTheDocument();
});

test.each([
  ["image/png", "img", "imageViewer.loadFailed"],
  ["video/webm", "video", "documents.videoLoadFailed"],
  ["audio/wav", "audio", "files.loadFailed"],
])(
  "%s failure offers a focused retry and resets for another file",
  (mime, tag, message) => {
    const props = {
      url: "/broken",
      mime_type: mime,
      size: 100,
      fileName: "broken",
    };
    const { container, rerender } = render(<BinaryFilePreview {...props} />);
    const media = container.querySelector(tag)!;
    fireEvent.error(media);
    expect(screen.getByRole("alert")).toHaveTextContent(i18n.t(message));
    const retry = screen.getByRole("button", { name: i18n.t("common.retry") });
    retry.focus();
    fireEvent.click(retry);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(container.querySelector(tag)).not.toBe(media);
    expect(document.activeElement).not.toBe(document.body);
    fireEvent.error(container.querySelector(tag)!);
    rerender(
      <BinaryFilePreview {...props} url="/another" fileName="another" />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(container.querySelector(tag)?.getAttribute("src")).toContain(
      "/another",
    );
    rerender(<BinaryFilePreview {...props} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  },
);

test("fallback download does not submit its enclosing skill form", () => {
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
  const download = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  render(
    <form onSubmit={submit}>
      <BinaryFilePreview
        url="/archive.zip"
        mime_type="application/zip"
        size={100}
        fileName="archive.zip"
      />
    </form>,
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: i18n.t("skills.binaryPreview.download"),
    }),
  );
  expect(download).toHaveBeenCalledOnce();
  expect(submit).not.toHaveBeenCalled();
  download.mockRestore();
});
