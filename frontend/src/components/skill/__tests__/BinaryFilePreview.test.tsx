/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { BinaryFilePreview } from "../BinaryFilePreview";

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
